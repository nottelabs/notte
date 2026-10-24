"""Builds the `DomNode` tree of a page from the payload of `buildDomNode.js`, in one pass.

Each node's role, id, text, attributes and selectors are computed once, while walking the payload
depth first. A node gets an id when the script highlighted it (`highlightIndex`) and its role is a
`NodeRole`: the role's short id (`L`, `B`, `I`, `F`, `O`, `M`) followed by a counter per short id,
in document order (child frames included, at the position of their iframe element).

Three text algorithms read the tree, with different outputs, and are kept as they are:
- `DomNode.text` (`element_name` below): accessible-name-like, e.g. the visible text of a link
- `DomNode.inner_text()`: the text of an interaction node, used as the action label
- `action_space.children_texts`: the text rendered in the action descriptions
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from notte_core.config import config
from notte_core.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.element_state import ElementState
from notte_core.highlighter import BoundingBox
from notte_core.logging import logger
from notte_core.node_type import NodeRole, NodeType
from typing_extensions import NotRequired, TypedDict

from notte_browser.dom.csspaths import build_csspath
from notte_browser.driver import ElementHandle


class RawNode(TypedDict):
    """One node of the `buildDomNode.js` payload (`{rootId, map}`, children given by id)."""

    # text nodes: `type` = "TEXT_NODE", `text` and `isInViewport` only (hidden text is not in the payload;
    # text rendered outside the viewport is, with `isInViewport` false)
    type: NotRequired[str]
    text: NotRequired[str]
    isInViewport: NotRequired[bool]
    # elements
    tagName: NotRequired[str]
    xpath: NotRequired[str]
    attributes: NotRequired[dict[str, str]]
    children: NotRequired[list[str]]
    isVisible: NotRequired[bool]
    isTopElement: NotRequired[bool]
    isInteractive: NotRequired[bool]
    isEditable: NotRequired[bool]
    disabledReason: NotRequired[str | None]
    # a disabled control that would be highlighted if it were enabled (it has no highlight index)
    disabled: NotRequired[bool]
    pointerElement: NotRequired[bool]
    highlightIndex: NotRequired[int]
    shadowRoot: NotRequired[bool]
    bbox: NotRequired[dict[str, float] | None]
    # live value / checked state / select options of highlighted and disabled elements (`ElementState`)
    state: NotRequired[dict[str, Any]]
    # accessible name of highlighted and disabled elements, when they have one
    accessibleName: NotRequired[str]
    # a highlighted element with a click handler of its own (`onclick`)
    clickHandler: NotRequired[bool]
    # visible iframe elements of the child frames the caller asked about
    frameIndex: NotRequired[int]
    frameOffset: NotRequired[dict[str, float]]
    # set by the parser: the child frame grafted under this iframe element
    frame: NotRequired["RawFrame"]
    # set by the parser on highlighted nodes when a selector generator is installed
    handle: NotRequired[ElementHandle | None]


@dataclass
class RawFrame:
    """The payload of one frame: its nodes by id, and the id of its root (the `<body>`)."""

    root_id: str
    nodes: dict[str, RawNode]


def build_dom_tree(frame: RawFrame, url: str) -> DomNode | None:
    """Builds the tree of the main frame (with its grafted child frames). `url` prefixes the notte selectors."""
    root = frame.nodes[frame.root_id]
    builder = _TreeBuilder(duplicates=duplicate_clickables(root, frame.nodes))
    return builder.build(root, frame.nodes, url)


# the short ids of the roles of real controls: links, buttons (tabs, checkboxes, ...), inputs and options
_CONTROL_SHORT_IDS = frozenset({"L", "B", "I", "O"})


@dataclass
class _Highlight:
    """A highlighted node, with the highlighted nodes nested in it."""

    index: int
    # a link, button, input or option; else a generic clickable (`M`), e.g. a `<div>` with a pointer cursor
    control: bool
    text: str
    name: str
    # it has a click handler of its own
    handler: bool
    children: list["_Highlight"] = field(default_factory=list)

    def descendants(self) -> list["_Highlight"]:
        return [node for child in self.children for node in (child, *child.descendants())]


def duplicate_clickables(root: RawNode, nodes: dict[str, RawNode]) -> set[int]:
    """The highlight indices of the generic clickables that duplicate a real control, which get no id.

    A pointer cursor makes an element clickable, and pages put one on containers around their controls. Such
    an element is a duplicate when it is:
    - inside a control (a link, a button, ...): clicking it clicks the control, unless it has a name or a
      click handler of its own;
    - around a single control, and named like it: its name, or else its text, is empty or the control's text
      or name (a `<div>Go</div>` around a "Go" button), unless it has a click handler of its own.
    """
    highlights = _highlights(root, nodes)
    duplicates: set[int] = set()

    def inside(node: _Highlight, in_control: bool) -> None:
        if in_control and not node.control and len(node.name) == 0 and not node.handler:
            duplicates.add(node.index)
        for child in node.children:
            inside(child, in_control or node.control)

    def around(node: _Highlight) -> None:
        # nested wrappers first: a wrapper around a wrapper of the control is then around the control alone
        for child in node.children:
            around(child)
        if node.control or node.handler or node.index in duplicates:
            return
        nested = [child for child in node.descendants() if child.index not in duplicates]
        label = node.name or node.text
        if len(nested) == 1 and nested[0].control and label in ("", nested[0].text, nested[0].name):
            duplicates.add(node.index)

    for node in highlights:
        inside(node, False)
        around(node)
    return duplicates


def _highlights(raw: RawNode, nodes: dict[str, RawNode]) -> list[_Highlight]:
    """The highlighted nodes under `raw` (itself included) that are not nested in another one, with their own
    nested highlighted nodes. Child frames are included."""
    children: list[_Highlight] = []
    for child_id in raw.get("children", []):
        child = nodes.get(child_id)
        if child is not None:
            children.extend(_highlights(child, nodes))
    frame = raw.get("frame")
    if frame is not None:
        children.extend(_highlights(frame.nodes[frame.root_id], frame.nodes))
    index = raw.get("highlightIndex")
    tag_name = raw.get("tagName")
    if index is None or tag_name is None:
        return children
    role = NodeRole.from_element(_tag(tag_name), raw.get("attributes", {}))
    control = isinstance(role, NodeRole) and role.short_id() in _CONTROL_SHORT_IDS
    name = _normalize(raw.get("accessibleName", ""))
    text = _normalize(_raw_text(raw, nodes))
    return [_Highlight(index, control, text, name, raw.get("clickHandler", False), children)]


def _raw_text(raw: RawNode, nodes: dict[str, RawNode]) -> str:
    if raw.get("type") == "TEXT_NODE":
        return raw.get("text", "")
    texts = (_raw_text(child, nodes) for child_id in raw.get("children", []) if (child := nodes.get(child_id)))
    return " ".join(texts)


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def _tag(tag_name: str) -> str:
    """The tag name of an element, with the `wiz_` prefix of Google's custom elements replaced."""
    if tag_name.startswith("wiz_"):
        return tag_name[len("wiz_") :].replace("_", "-")
    return tag_name


@dataclass
class _TreeBuilder:
    # the highlight indices of the nodes that get no id (see `duplicate_clickables`)
    duplicates: set[int] = field(default_factory=set)
    id_counters: defaultdict[str, int] = field(default_factory=lambda: defaultdict(lambda: 1))

    def build(self, root: RawNode, nodes: dict[str, RawNode], url: str) -> DomNode | None:
        return self.node(
            root,
            nodes,
            in_iframe=False,
            in_shadow_root=False,
            iframe_parent_css_paths=[],
            notte_selector=url,
        )

    def next_id(self, role: NodeRole) -> str:
        prefix = role.short_id(force_id=True)
        assert prefix is not None
        number = self.id_counters[prefix]
        self.id_counters[prefix] = number + 1
        return f"{prefix}{number}"

    def node(
        self,
        raw: RawNode,
        nodes: dict[str, RawNode],
        in_iframe: bool,
        in_shadow_root: bool,
        iframe_parent_css_paths: list[str],
        notte_selector: str,
    ) -> DomNode | None:
        if raw.get("type") == "TEXT_NODE":
            return DomNode(
                id=None,
                type=NodeType.TEXT,
                role=NodeRole.TEXT,
                text=raw["text"],  # pyright: ignore[reportTypedDictNotRequiredAccess]
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(in_viewport=raw["isInViewport"]),  # pyright: ignore[reportTypedDictNotRequiredAccess]
            )

        tag_name = raw.get("tagName")
        attributes = raw.get("attributes", {})
        child_ids = raw.get("children", [])
        xpath = raw.get("xpath")
        if tag_name is None:
            if xpath is None and len(attributes) == 0 and len(child_ids) == 0:
                return None
            raise ValueError(f"Tag name is None for node: {raw}")
        if xpath is None:
            raise ValueError(f"XPath is None for node: {raw}")

        highlight_index = raw.get("highlightIndex")
        if highlight_index in self.duplicates:
            highlight_index = None
        # the CSS path and the iframe check read the tag and attributes as the script returned them
        css_path = build_csspath(tag_name=tag_name, xpath=xpath, attributes=attributes, highlight_index=highlight_index)
        notte_selector = ":".join([notte_selector, str(hash(xpath)), str(hash(css_path))])
        shadow_root = raw.get("shadowRoot", False)
        if shadow_root:
            in_shadow_root = True
        selectors = NodeSelectors(
            css_selector=css_path,
            xpath_selector=xpath,
            notte_selector=notte_selector,
            # an iframe element is in an iframe only if its own document is
            in_iframe=in_iframe,
            iframe_parent_css_selectors=iframe_parent_css_paths,
            in_shadow_root=in_shadow_root,
        )
        if tag_name.lower() == "iframe":
            # the children of an iframe element are the (grafted) frame's document
            in_iframe = True
            in_shadow_root = False
            iframe_parent_css_paths = iframe_parent_css_paths + [css_path]

        tag_name = _tag(tag_name)
        attributes = cleanup_aria_attributes(attributes)
        if len(tag_name) == 0 and not attributes.get("role") and (len(attributes) > 0 or len(child_ids) > 0):
            raise ValueError(f"No tag_name found for element with attributes: {attributes}")
        role = NodeRole.from_element(tag_name, attributes)

        node_id: str | None = None
        if highlight_index is not None:
            if isinstance(role, NodeRole):
                node_id = self.next_id(role)
            else:
                logger.debug(f"Unsupported role to convert to ID: {role!r} (<{tag_name}>). Add it to NodeRole.")

        children: list[DomNode] = []
        for child_id in child_ids:
            child_raw = nodes.get(child_id)
            if child_raw is None:
                continue
            child = self.node(child_raw, nodes, in_iframe, in_shadow_root, iframe_parent_css_paths, notte_selector)
            if child is not None:
                children.append(child)
        frame = raw.get("frame")
        if frame is not None:
            child = self.node(
                frame.nodes[frame.root_id],
                frame.nodes,
                in_iframe,
                in_shadow_root,
                iframe_parent_css_paths,
                notte_selector,
            )
            if child is not None:
                children.append(child)

        bbox = raw.get("bbox")
        if highlight_index is not None and config.highlight_elements:
            assert bbox is not None, "Bbox is required for highlighted elements"
        node = DomNode(
            id=node_id,
            type=NodeType.INTERACTION
            if raw.get("isInteractive", False) and highlight_index is not None
            else NodeType.OTHER,
            role=role,
            text=element_name(tag_name, attributes, children),
            children=children,
            attributes=DomAttributes.safe_init(tag_name=tag_name, **attributes),
            computed_attributes=ComputedDomAttributes(
                in_viewport=raw.get("isVisible", False),
                is_editable=raw.get("isEditable", False),
                shadow_root=shadow_root,
                handle=raw.get("handle"),
                selectors=selectors,
            ),
            bbox=BoundingBox.model_validate(bbox) if bbox else None,
            state=ElementState.from_payload(raw.get("state")),
            accessible_name=raw.get("accessibleName"),
            disabled=raw.get("disabled", False),
        )
        for child in children:
            child.set_parent(node)
        return node


def cleanup_aria_attributes(attrs: dict[str, str]) -> dict[str, str]:
    """Renames the attributes containing `aria-` to start with it (e.g. `x-aria-label` -> `aria-label`).

    The renamed attributes move to the end of `attrs`, which is modified in place.
    """
    to_add: dict[str, str] = {}
    to_remove: list[str] = []
    pattern = "aria-"
    for attr, value in attrs.items():
        if pattern in attr:
            # remove anything before aria_
            new_attr = pattern + pattern.join(attr.split(pattern)[1:])
            if new_attr in attrs and attrs[new_attr] != value:
                logger.debug(f"Key {new_attr} got updated while loading: old={attrs[new_attr]}, new={value}")
            to_add[new_attr] = value
            to_remove.append(attr)
    for attr in to_remove:
        del attrs[attr]
    for attr, value in to_add.items():
        attrs[attr] = value
    return attrs


_LABEL_ATTRIBUTES = ("name", "title", "alt", "placeholder", "value")


def element_name(tag_name: str, attributes: dict[str, str], children: Sequence[DomNode]) -> str:
    """The name of an element (its `DomNode.text`), from its labelling attributes or its visible text."""
    aria_label = attributes.get("aria-label")
    if aria_label:
        return aria_label
    for attr in _LABEL_ATTRIBUTES:
        value = attributes.get(attr)
        if value and value.strip():
            return value.strip()
    tag = tag_name.lower()
    if tag in ("button", "a", "label"):
        text = "".join(visible_text(child) for child in children).strip()
        if len(text) > 0:
            return text
    if tag in ("img", "a"):
        if "src" in attributes:
            return attributes["src"]
        if "href" in attributes:
            return attributes["href"]
    if tag == "body":
        # usually in accessibility mode, the WebArea name is the page title
        return "body content"
    if tag == "button":
        return attributes.get("type") or ""
    return ""


def visible_text(node: DomNode) -> str:
    """The concatenated text of the visible text nodes under `node`."""
    if node.type is NodeType.TEXT:
        return node.text if node.computed_attributes.in_viewport else ""
    return "".join(visible_text(child) for child in node.children)
