from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, NodeSelectors
from notte_core.browser.dom_tree import DomNode as NotteDomNode
from notte_core.browser.node_type import NodeRole, NodeType
from typing_extensions import override

VERBOSE = False


# clean up aria attributes
def cleanup_aria_attributes(attrs: dict[str, str]) -> dict[str, str]:
    to_add: dict[str, str] = {}
    to_remove: list[str] = []
    pattern = "aria-"
    for attr, value in attrs.items():
        if pattern in attr:
            # remove anything before aria_
            new_attr_split = attr.split(pattern)[1:]
            new_attr = pattern + (pattern.join(new_attr_split))
            if new_attr in attrs and attrs[new_attr] != value:
                logger.debug(f"Key {new_attr} got updated while loading: old={attrs[new_attr]}, new={value}")

            to_add[new_attr] = value
            to_remove.append(attr)
    for attr in to_remove:
        del attrs[attr]
    for attr, value in to_add.items():
        attrs[attr] = value
    return attrs


@dataclass(frozen=False)
class DOMBaseNode:
    parent: "DOMElementNode | None"
    is_visible: bool
    highlight_index: int | None
    notte_id: str | None = field(init=False, default=None)
    children: list["DOMBaseNode"] = field(init=False, default_factory=list)
    # Use None as default and set parent later to avoid circular reference issues

    def __post_init__(self) -> None:
        self.children = [] if getattr(self, "children", None) is None else self.children
        self.notte_id = None if getattr(self, "notte_id", None) is None else self.notte_id

    def to_dict(self) -> dict[str, str]:
        raise NotImplementedError("to_dict method not implemented for DOMBaseNode")

    def to_notte_domnode(self) -> NotteDomNode:
        raise NotImplementedError("to_notte_domnode method not implemented for DOMBaseNode")

    @property
    def name(self) -> str:
        raise NotImplementedError("name property not implemented for DOMBaseNode")

    @property
    def role(self) -> str:
        raise NotImplementedError("role property not implemented for DOMBaseNode")


@dataclass(frozen=False)
class DOMTextNode(DOMBaseNode):
    text: str = ""
    type: str = "TEXT_NODE"
    highlight_index: int | None = None

    def has_parent_with_highlight_index(self) -> bool:
        current = self.parent
        while current is not None:
            if current.highlight_index is not None:
                return True
            current = current.parent
        return False

    @override
    def to_dict(self) -> dict[str, str]:
        return {
            "role": "text",
            "text": self.text,
        }

    @property
    @override
    def role(self) -> str:
        return "text"

    @property
    @override
    def name(self) -> str:
        return self.text

    @override
    def to_notte_domnode(self) -> NotteDomNode:
        return NotteDomNode(
            id=self.notte_id,
            role=NodeRole.from_value(self.role),
            type=NodeType.TEXT,
            text=self.name,
            children=[],
            computed_attributes=ComputedDomAttributes(
                in_viewport=self.is_visible,
            ),
            attributes=None,
        )


@dataclass(frozen=False)
class DOMElementNode(DOMBaseNode):
    """
    xpath: the xpath of the element from the last root node
    (shadow root or iframe OR document if no shadow root or iframe).
    To properly reference the element we need to recursively switch the root node
    until we find the element (work you way up the tree with `.parent`)
    """

    tag_name: str
    xpath: str
    # iframe resolution
    in_iframe: bool
    in_shadow_root: bool
    css_path: str
    iframe_parent_css_selectors: list[str]
    notte_selector: str
    # html attributes
    attributes: dict[str, str]
    # computed attributes
    is_interactive: bool = False
    is_top_element: bool = False
    shadow_root: bool = False
    is_editable: bool = False

    @override
    def __post_init__(self) -> None:
        if self.tag_name is not None and self.tag_name.startswith("wiz_"):  # type: ignore[arg-type]
            self.tag_name = self.tag_name[len("wiz_") :].replace("_", "-")
        # replace also in the attributes
        self.attributes = cleanup_aria_attributes(self.attributes)

    @override
    def __repr__(self) -> str:
        tag_str = f"<{self.tag_name}"

        # Add attributes
        for key, value in self.attributes.items():
            tag_str += f' {key}="{value}"'
        tag_str += ">"

        # Add extra info
        extras: list[str] = []
        if self.is_interactive:
            extras.append("interactive")
        if self.is_top_element:
            extras.append("top")
        if self.shadow_root:
            extras.append("shadow-root")
        if self.highlight_index is not None:
            extras.append(f"highlight:{self.highlight_index}")

        if extras:
            tag_str += f" [{', '.join(extras)}]"

        return tag_str

    @property
    @override
    def role(self) -> str:
        # transform to axt role
        if self.attributes.get("role"):
            return self.attributes["role"]
        if self.tag_name is None or len(self.tag_name) == 0:  # type: ignore[arg-type]
            if len(self.attributes) == 0 and len(self.children) == 0:
                return "none"
            raise ValueError(f"No tag_name found for element: {self} with attributes: {self.attributes}")
        clean_tag_name = self.tag_name.lower().replace("-", "").replace("_", "")
        match self.tag_name.lower():
            # Structural elements
            case "body":
                return "WebArea"
            case "nav":
                return "navigation"
            case "main":
                return "main"
            case "header":
                return "banner"
            case "footer":
                return "contentinfo"
            case "aside":
                return "complementary"
            case "section" | "article":
                return "article"
            case "div":
                return "group"

            # Interactive elements
            case "a":
                return "link"
            case "button":
                return "button"
            case "input":
                input_type = self.attributes.get("type", "text").lower()
                match input_type:
                    # TODO: could create a special type for submit/reset
                    case "button" | "submit" | "reset":
                        return "button"
                    case "radio":
                        return "radio"
                    case "checkbox":
                        return "checkbox"
                    case "search":
                        return "searchbox"
                    case _:
                        return "textbox"
            case "select":
                return "combobox"
            case "textarea":
                return "textbox"
            case "option":
                return "option"

            # Text elements
            case "h1" | "h2" | "h3" | "h4" | "h5" | "h6":
                return "heading"
            case "p":
                return "paragraph"
            case "span" | "strong" | "em" | "small" | "bdi" | "i":
                return "text"
            case "label":
                return "LabelText"
            case "blockquote":
                return "blockquote"
            case "code" | "pre":
                return "code"
            case "time":
                return "time"
            case "br":
                return "LineBreak"

            # List elements
            case "ul" | "ol" | "dl":
                return "list"
            case "li":
                return "listitem"
            case "dt" | "dd":
                return "listitem"

            # Table elements
            case "table":
                return "table"
            case "tr":
                return "row"
            case "td":
                return "cell"
            case "th":
                return "columnheader"
            case "thead" | "tbody" | "tfoot":
                return "rowgroup"

            # Media elements
            case "img":
                return "img"
            case "figure":
                return "figure"
            case "iframe":
                return "Iframe"

            # Form elements
            case "form":
                return "form"
            case "fieldset":
                return "group"
            case "dialog":
                return "dialog"
            case "progress":
                return "progressbar"
            case "meter":
                return "meter"

            # Menu elements
            case "menu":
                return "menu"
            case "menuitem":
                return "menuitem"

            # Default case
            case "hr":
                return "separator"
            case _:
                roles_to_check = ["menuitemcheckbox", "menuitemradio", "menuitem", "menu", "dialog"]
                for role in roles_to_check:
                    if role in clean_tag_name:
                        return role
                if "popup" in clean_tag_name:
                    return "MenuListPopup"

                if VERBOSE:
                    logger.warning(f"No role found for tag: {self.tag_name} with attributes: {self.attributes}")
                return "generic"

    @property
    @override
    def name(self) -> str:
        if len(self.attributes) == 0:
            return ""
        # Check explicit ARIA labeling
        if "aria-label" in self.attributes:
            if len(self.attributes["aria-label"]) > 0:
                return self.attributes["aria-label"]

        # Check for text content for certain elements
        if self.tag_name.lower() in ["button", "a", "label"]:
            text_content = self._get_text_content().strip()
            if len(text_content) > 0:
                return text_content

        # Check for button/input value
        if self.tag_name.lower() in ["button", "input"]:
            if "value" in self.attributes:
                value = self.attributes.get("value")
                if value and len(value.strip()) > 0:
                    return value.strip()

        # Check for standard labeling attributes
        for attr in ["name", "title", "alt", "placeholder", "value"]:
            if attr in self.attributes:
                value = self.attributes.get(attr)
                if value and value.strip():
                    return value.strip()

        # Check aria-labelledby if present
        # if "aria-labelledby" in self.attributes:
        #     # Note: This would require access to other elements
        #     # TODO: Implement aria-labelledby resolution
        #     pass

        if self.tag_name.lower() in ["img", "a"]:
            if "src" in self.attributes:
                return self.attributes["src"]
            if "href" in self.attributes:
                return self.attributes["href"]

        if self.tag_name.lower() in ["body"]:
            # Usually in accessibility mode, the WebArea name is the page title
            # TODO: get the page title from the browser
            return "body content"

        if self.tag_name.lower() in [
            "main",
            "div",
            "section",
            "article",
            "header",
            "footer",
            "aside",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "span",
            "label",
            "strong",
            "em",
            "small",
            "bdi",
            "li",
            "ol",
            "ul",
            "dl",
            "dt",
            "dd",
            "table",
            "tr",
            "td",
            "th",
            "thead",
            "tbody",
            "tfoot",
            "img",
            "figure",
            "iframe",
            "form",
            "fieldset",
            "dialog",
            "progress",
            "meter",
            "menu",
            "menuitem",
            "hr",
            "br",
            "p",
            "i",
        ]:
            # TODO: create a better name computation using text children and attributes
            return ""

        if self.tag_name.lower() in ["footer"]:
            return self.tag_name

        if self.tag_name.lower() in ["button"]:
            return self.attributes.get("type") or ""

        first_5_attrs = list(self.attributes.items())[:5]
        if VERBOSE:
            logger.error(f"No name found for element: {self} with attributes: {first_5_attrs}")
        return ""

    def _get_text_content(self) -> str:
        """Recursively get text content from child text nodes."""

        def extract_text(node: DOMBaseNode) -> str:
            if isinstance(node, DOMTextNode):
                return node.text if node.is_visible else ""
            else:
                children_text = "".join(extract_text(child) for child in node.children)
                return children_text

        result = extract_text(self)
        return result

    @override
    def to_dict(self) -> dict[str, Any]:
        role, name = self.role, self.name
        if (name == "" or role == "") and len(self.children) == 0:
            return {}
        base: dict[str, Any] = {"role": role, "name": name}
        if self.children:
            base["children"] = [child.to_dict() for child in self.children]
        return base

    @override
    def to_notte_domnode(self) -> NotteDomNode:
        node = NotteDomNode(
            id=self.notte_id,
            type=NodeType.INTERACTION if self.is_interactive else NodeType.OTHER,
            role=NodeRole.from_value(self.role),
            text=self.name,
            children=[child.to_notte_domnode() for child in self.children],
            attributes=DomAttributes.safe_init(
                tag_name=self.tag_name,
                **self.attributes,
            ),
            computed_attributes=ComputedDomAttributes(
                in_viewport=self.is_visible,
                is_interactive=self.is_interactive,
                is_top_element=self.is_top_element,
                is_editable=self.is_editable,
                shadow_root=self.shadow_root,
                highlight_index=self.highlight_index,
                selectors=NodeSelectors(
                    css_selector=self.css_path,
                    xpath_selector=self.xpath,
                    notte_selector=self.notte_selector,
                    in_iframe=self.in_iframe,
                    iframe_parent_css_selectors=self.iframe_parent_css_selectors,
                    in_shadow_root=self.in_shadow_root,
                ),
            ),
        )
        # second path to set the parent
        for child in node.children:
            child.set_parent(node)
        return node
