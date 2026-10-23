import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from functools import cached_property
from typing import Annotated, Any, Callable, ClassVar, TypeAlias

from pydantic import BaseModel, Field
from typing_extensions import override

from notte_core.element_state import ElementState
from notte_core.highlighter import BoundingBox
from notte_core.logging import logger
from notte_core.node_type import NodeRole, NodeType


class NodeSelectors(BaseModel):
    css_selector: str
    xpath_selector: str
    in_iframe: bool
    in_shadow_root: bool
    notte_selector: str | None = None
    iframe_parent_css_selectors: list[str]
    playwright_selector: str | None = None
    python_selector: str | None = None

    def selectors(self) -> list[str]:
        selector_list: list[str] = []
        if self.playwright_selector is not None and len(self.playwright_selector) > 0:
            selector_list.append(self.playwright_selector)
        if len(self.css_selector) > 0:
            selector_list.append(f"css={self.css_selector}")
        if len(self.xpath_selector) > 0:
            selector_list.append(f"xpath={self.xpath_selector}")
        return selector_list

    @staticmethod
    def from_unique_selector(unique_selector: str) -> "NodeSelectors":
        css_selector = ""
        xpath_selector = ""
        playwright_selector: str | None = None
        if unique_selector.startswith("xpath="):
            xpath_selector = unique_selector.removeprefix("xpath=")
        elif unique_selector.startswith("css="):
            css_selector = unique_selector.removeprefix("css=")
        elif unique_selector.startswith("internal:"):
            playwright_selector = unique_selector
        elif unique_selector.startswith("~"):
            text = unique_selector.replace("~", "").strip()
            playwright_selector = f'internal:text="{text}"'
        else:
            playwright_selector = unique_selector

        return NodeSelectors(
            css_selector=css_selector,
            xpath_selector=xpath_selector,
            playwright_selector=playwright_selector,
            notte_selector="",
            in_iframe=False,
            in_shadow_root=False,
            iframe_parent_css_selectors=[],
            python_selector="",
        )


# Type alias for clarity
AttributeValue: TypeAlias = str | int | bool | None
AttributeValues: TypeAlias = list[AttributeValue]


_dom_errors: dict[str, AttributeValues] = {}
_MAX_DOM_ERROR_SAMPLES = 5


def add_dom_errors(extra_keys: set[str], values: dict[str, AttributeValue]) -> None:
    """
    Add an error to the buffer, consolidating the values.
    Each attribute will store up to _max_samples_per_key unique values.
    """

    for key in extra_keys:
        if key not in _dom_errors.keys():
            _dom_errors[key] = []
        str_v = str(values[key])[:50]
        if len(_dom_errors[key]) < _MAX_DOM_ERROR_SAMPLES and str_v not in _dom_errors[key]:
            _dom_errors[key].append(str_v)


def flush_dom_errors() -> None:
    """Flush all buffered error messages in a consolidated format."""
    if len(_dom_errors) == 0:
        return

    logger.debug(
        f"""
Extra DOM attributes found: {list(_dom_errors.keys())}.
Sample values:
{_dom_errors}
These attributes should be added to the DomAttributes class. Fix this ASAP.
"""
    )
    # Clear the buffer
    _dom_errors.clear()


@dataclass
class DomAttributes:
    # State attributes
    modal: bool | None
    required: bool | None
    visible: bool | None
    selected: bool | None
    checked: bool | None
    enabled: bool | None
    focused: bool | None
    disabled: bool | None
    pressed: bool | None
    type: str | None

    # Value attributes
    value: str | None
    valuemin: str | None
    valuemax: str | None
    description: str | None
    autocomplete: str | None
    haspopup: bool | None
    accesskey: str | None
    autofocus: bool | None
    tabindex: int | None
    multiselectable: bool | None

    # HTML element attributes
    tag_name: str
    class_name: str | None
    id_name: str | None  # stores the id attribute

    # Resource attributes
    href: str | None
    src: str | None
    srcset: str | None
    target: str | None
    ping: str | None
    data_src: str | None
    data_srcset: str | None
    label_for: str | None  # stores the for attribute

    # Text attributes
    placeholder: str | None
    title: str | None
    alt: str | None
    name: str | None
    autocorrect: str | None
    autocapitalize: str | None
    spellcheck: bool | None
    maxlength: int | None

    # Layout attributes
    width: int | None
    height: int | None
    size: int | None
    rows: int | None

    # Internationalization attributes
    lang: str | None
    dir: str | None

    # aria attributes
    action: str | None
    role: str | None
    aria_label: str | None
    aria_labelledby: str | None
    aria_describedby: str | None
    aria_hidden: bool | None
    aria_expanded: bool | None
    aria_controls: str | None
    aria_haspopup: bool | None
    aria_current: str | None
    aria_autocomplete: str | None
    aria_selected: bool | None
    aria_modal: bool | None
    aria_disabled: bool | None
    aria_valuenow: int | None
    aria_live: str | None
    aria_atomic: bool | None
    aria_valuemax: int | None
    aria_valuemin: int | None
    aria_level: int | None
    aria_owns: str | None
    aria_multiselectable: bool | None
    aria_colindex: int | None
    aria_colspan: int | None
    aria_rowindex: int | None
    aria_rowspan: int | None
    aria_description: str | None
    aria_activedescendant: str | None
    hidden: bool | None
    expanded: bool | None

    @staticmethod
    def safe_init(**kwargs: AttributeValue) -> "DomAttributes":
        # compute additional attributes
        if "class" in kwargs:
            kwargs["class_name"] = kwargs["class"]
            del kwargs["class"]

        if "id" in kwargs:
            kwargs["id_name"] = kwargs["id"]
            del kwargs["id"]

        if "for" in kwargs:
            kwargs["label_for"] = kwargs["for"]
            del kwargs["for"]

        # replace '-' with '_' in keys
        kwargs = {
            k.replace("-", "_"): v
            for k, v in kwargs.items()
            if (
                not k.startswith("data-")
                and not k.startswith("js")
                and not k.startswith("__")
                and not k.startswith("g-")
            )
        }

        keys = set(DomAttributes.__dataclass_fields__.keys())
        excluded_keys = set(
            [
                "browser_user_highlight_id",
                "class",
                "style",
                "data_jsl10n",
                "keyshortcuts",
                "rel",
                "ng_non_bindable",
                "c_wiz",
                "ssk",
                "soy_skip",
                "key",
                "method",
                "eid",
                "view",
                "pivot",
            ]
        )

        extra_keys = set(kwargs.keys()).difference(keys).difference(excluded_keys)
        if len(extra_keys) > 0:
            add_dom_errors(extra_keys, kwargs)

        return DomAttributes(**{key: kwargs.get(key, None) for key in keys})  # type: ignore[arg-type]

    def relevant_attrs(
        self,
        include_attributes: frozenset[str] | None = None,
        max_len_per_attribute: int | None = None,
    ) -> dict[str, str | bool | int]:
        disabled_attrs = set(
            [
                "tag_name",
                "class_name",
                "width",
                "height",
                "size",
                "lang",
                "dir",
                "action",
                "role",
                "aria_label",
                "name",
            ]
        ).difference(include_attributes or frozenset())
        attrs: dict[str, str | bool | int] = {}
        for attribute in fields(self):
            key = attribute.name
            value: AttributeValue = getattr(self, key)
            if (
                key not in disabled_attrs
                and (include_attributes is None or key in include_attributes)
                and value is not None
            ):
                if max_len_per_attribute is not None and isinstance(value, str) and len(value) > max_len_per_attribute:
                    value = value[:max_len_per_attribute] + "..."
                attrs[key] = value
        return attrs

    @override
    def __repr__(self) -> str:
        # only display relevant attributes
        attrs = self.relevant_attrs()
        return f"{self.__class__.__name__}({attrs})"


@dataclass(frozen=True)
class ComputedDomAttributes:
    in_viewport: bool = False
    is_editable: bool = False
    shadow_root: bool = False
    selectors: NodeSelectors | None = None
    # Live element handle, only kept when a selector generator is installed
    # (see `notte_browser.resolution.set_selector_generator`). Never serialised.
    handle: Annotated[Any, Field(exclude=True)] = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class DomNode:
    id: str | None
    type: NodeType
    role: NodeRole | str
    text: str
    children: list["DomNode"]
    attributes: DomAttributes | None
    computed_attributes: ComputedDomAttributes
    bbox: BoundingBox | None = None
    # parents cannot be set in the constructor because it is a recursive structure
    # we need to set it after the constructor
    parent: "DomNode | None" = None
    # live value / checked state / select options of an interactive element (see `element_state.py`)
    state: ElementState | None = None
    # accessible name of an interactive element, as the browser computes it for screen readers
    # (`aria-labelledby`, `<label>`, `aria-label`, `alt`, text content, ...); None when it has none
    accessible_name: str | None = None
    # a disabled control (`disabled`, in a disabled `<fieldset>`, or `aria-disabled="true"`): it has no
    # id and no action, and is rendered in the action space description with a `disabled` attribute
    disabled: bool = False

    @override
    def __repr__(self) -> str:
        # only display relevant attributes
        # recursively display children + indent
        children_repr = "\n".join([f"  {child.__repr__()}" for child in self.children])
        return f"{self.__class__.__name__}(id={self.id}, role={self.get_role_str()}, text={self.text[:40]}...)\n{children_repr}"

    def __post_init__(self) -> None:
        if isinstance(self.role, str):
            object.__setattr__(self, "role", NodeRole.from_value(self.role))

    def set_parent(self, parent: "DomNode | None") -> None:
        object.__setattr__(self, "parent", parent)

    def inner_text(self, depth: int = 3) -> str:
        if self.attributes is not None and self.attributes.tag_name.lower() == "input":
            return self.text or self.attributes.placeholder or ""

        if self.type == NodeType.TEXT:
            return self.text
        texts: list[str] = []
        for child in self.children:
            # inner text is not allowed to be hidden
            # or not visible
            # or disabled
            child_text = child.inner_text(depth=depth - 1)
            if len(child_text) == 0:
                continue
            elif child.attributes is None:
                texts.append(child_text)
            elif child.attributes.hidden is not None and not child.attributes.hidden:
                continue
            elif child.attributes.visible is not None and not child.attributes.visible:
                continue
            elif child.attributes.enabled is not None and not child.attributes.enabled:
                continue
            else:
                texts.append(child_text)
        return " ".join(texts)

    def get_role_str(self) -> str:
        if isinstance(self.role, str):
            return self.role
        return self.role.value

    # each element on the path from the root appends `:<hash(xpath)>:<hash(css_path)>` to the page url
    _NOTTE_SELECTOR_HASHES: ClassVar[re.Pattern[str]] = re.compile(r"(?::-?\d+:-?\d+)+$")

    def get_url(self) -> str | None:
        attr = self.computed_attributes.selectors
        if attr is None or attr.notte_selector is None or len(attr.notte_selector) == 0:
            return None
        return self._NOTTE_SELECTOR_HASHES.sub("", attr.notte_selector, count=1)

    def find(self, id: str) -> "DomNode | None":
        if self.id == id:
            return self
        for child in self.children:
            found = child.find(id)
            if found:
                return found
        return None

    def is_interaction(self) -> bool:
        if isinstance(self.role, str):
            return False
        if self.id is None:
            return False
        if self.type.value == NodeType.INTERACTION.value:
            return True
        return self.role.is_interactive()

    @classmethod
    def empty_root(cls) -> "DomNode":
        """Create an empty root DomNode for scraping (skips DOM tree computation)."""
        return cls(
            id=None,
            type=NodeType.OTHER,
            role=NodeRole.GENERIC,
            text="",
            children=[],
            attributes=None,
            computed_attributes=ComputedDomAttributes(),
        )

    def flatten(self, keep_filter: Callable[["DomNode"], bool] | None = None) -> list["DomNode"]:
        def inner(node: DomNode, acc: list["DomNode"]) -> list["DomNode"]:
            if keep_filter is None or keep_filter(node):
                acc.append(node)
            for child in node.children:
                _ = inner(child, acc)
            return acc

        return inner(self, [])

    @cached_property
    def _index(self) -> tuple[dict[str, "DomNode"], tuple["DomNode", ...]]:
        """Index a completed snapshot tree once; its children must not be mutated afterwards.

        Build lazily so BrowserWindow's synthetic download node is already inserted. The cache
        belongs to this root, so replacing a snapshot's root cannot reuse another tree's index.
        It contains references only and is not a dataclass field (or part of serialization).
        """
        interactions: dict[str, DomNode] = {}
        dialogs: list[DomNode] = []

        def visit(node: DomNode) -> bool:
            has_interaction = node.is_interaction()
            if has_interaction:
                assert node.id is not None
                interactions[node.id] = node
            dialog_start = len(dialogs)
            for child in node.children:
                has_interaction = visit(child) or has_interaction
            if node.role == NodeRole.DIALOG and node.computed_attributes.in_viewport and has_interaction:
                # An eligible outer dialog replaces its nested dialogs, retaining document order.
                dialogs[dialog_start:] = [node]
            return has_interaction

        _ = visit(self)
        return interactions, tuple(dialogs) if dialogs else (self,)

    @property
    def interaction_nodes_by_id(self) -> Mapping[str, "DomNode"]:
        """The completed tree's interaction nodes in document order, indexed by action id."""
        return self._index[0]

    def prune_non_dialogs_if_present(self) -> Sequence["DomNode"]:
        """Return topmost visible dialogs with interactions, or the root, from the shared index."""
        return self._index[1]

    def interaction_nodes(self) -> Sequence["DomNode"]:
        """Return the original interaction nodes in document order, retaining children and ancestry.

        Use `inner_text()` for action labels; `text` is the element's accessible-name-like value.
        """
        return tuple(self.interaction_nodes_by_id.values())
