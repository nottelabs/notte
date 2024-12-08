import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Required, TypedDict


class NodeCategory(Enum):
    STRUCTURAL = "structural"
    TEXT = "text"
    INTERACTION = "interaction"
    TABLE = "table"
    LIST = "list"
    OTHER = "other"
    PARAMETERS = "parameters"

    def roles(self, add_group_role: bool = False) -> set[str]:
        roles: set[str] = set()
        match self.value:
            case NodeCategory.INTERACTION.value:
                roles = {
                    "button",
                    "link",
                    "combobox",
                    "listbox",
                    "textbox",
                    "checkbox",
                    "searchbox",
                    "radio",
                    "tab",
                }
            case NodeCategory.TEXT.value:
                roles = {"text", "heading", "paragraph"}
            case NodeCategory.LIST.value:
                roles = {"list", "listitem", "listmarker"}
            case NodeCategory.TABLE.value:
                roles = {"table", "row", "column", "cell"}
            case NodeCategory.OTHER.value:
                pass
            case NodeCategory.STRUCTURAL.value:
                roles = {"group", "generic", "none", "navigation", "banner", "WebArea", "dialog"}
            case NodeCategory.PARAMETERS.value:
                roles = {"option"}
            case _:
                raise ValueError(f"No roles for category {self}")
        if add_group_role:
            roles.update(["group", "generic", "none"])
        return roles


class NodeRole(Enum):
    # structural
    WEBAREA = "WebArea"
    GROUP = "group"
    GENERIC = "generic"
    NONE = "none"
    NAVIGATION = "navigation"
    BANNER = "banner"
    DIALOG = "dialog"

    # text
    TEXT = "text"
    HEADING = "heading"
    PARAGRAPH = "paragraph"

    # interaction
    BUTTON = "button"
    LINK = "link"
    COMBOBOX = "combobox"
    LISTBOX = "listbox"
    TEXTBOX = "textbox"
    CHECKBOX = "checkbox"
    SEARCHBOX = "searchbox"
    RADIO = "radio"
    TAB = "tab"

    # parameters
    OPTION = "option"

    # table
    TABLE = "table"
    ROW = "row"
    COLUMN = "column"
    CELL = "cell"

    # list
    LIST = "list"
    LISTITEM = "listitem"
    LISTMARKER = "listmarker"

    @staticmethod
    def from_value(value: str) -> "NodeRole | str":
        if value.upper() in NodeRole.__members__:
            return NodeRole[value.upper()]
        return value

    def category(self) -> NodeCategory:
        match self.value:
            case NodeRole.TEXT.value | NodeRole.HEADING.value | NodeRole.PARAGRAPH.value:
                return NodeCategory.TEXT
            case NodeRole.OPTION.value:
                return NodeCategory.PARAMETERS
            case (
                NodeRole.WEBAREA.value
                | NodeRole.GROUP.value
                | NodeRole.GENERIC.value
                | NodeRole.NONE.value
                | NodeRole.NAVIGATION.value
                | NodeRole.BANNER.value
                | NodeRole.DIALOG.value
            ):
                return NodeCategory.STRUCTURAL
            case NodeRole.LIST.value | NodeRole.LISTITEM.value | NodeRole.LISTMARKER.value:
                return NodeCategory.LIST
            case NodeRole.TABLE.value | NodeRole.ROW.value | NodeRole.COLUMN.value | NodeRole.CELL.value:
                return NodeCategory.TABLE
            case (
                NodeRole.BUTTON.value
                | NodeRole.LINK.value
                | NodeRole.COMBOBOX.value
                | NodeRole.TEXTBOX.value
                | NodeRole.CHECKBOX.value
                | NodeRole.SEARCHBOX.value
                | NodeRole.RADIO.value
                | NodeRole.TAB.value
                | NodeRole.LISTBOX.value
            ):
                return NodeCategory.INTERACTION
            case _:
                return NodeCategory.OTHER


@dataclass
class HtmlSelector:
    playwright_selector: str
    css_selector: str
    xpath_selector: str


@dataclass
class NodeAttributesPre:
    modal: bool | None = None
    required: bool | None = None
    description: str | None = None
    visible: bool | None = None
    selected: bool | None = None
    checked: bool | None = None
    enabled: bool | None = None
    path: str | None = None


@dataclass
class NotteAttributesPost:
    selectors: HtmlSelector | None = None
    editable: bool = False
    input_type: str | None = None
    text: str | None = None


@dataclass
class NotteNode:
    id: str | None
    role: NodeRole | str
    text: str
    subtree_ids: list[str] = field(init=False, default_factory=list)
    children: list["NotteNode"] = field(default_factory=list)
    attributes_pre: NodeAttributesPre = field(default_factory=NodeAttributesPre)
    attributes_post: NotteAttributesPost | None = None

    def __post_init__(self) -> None:
        subtree_ids: list[str] = [] if self.id is None else [self.id]
        for child in self.children:
            subtree_ids.extend(child.subtree_ids)
        self.subtree_ids = subtree_ids

    def get_role_str(self) -> str:
        if isinstance(self.role, str):
            return self.role
        return self.role.value

    def find(self, id: str) -> "NotteNode | None":
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
        return self.role.category().value == NodeCategory.INTERACTION.value

    def flatten(self, only_interaction: bool = False) -> list["NotteNode"]:
        base: list["NotteNode"] = [self] if not only_interaction or self.is_interaction() else []
        return base + [node for child in self.children for node in child.flatten(only_interaction)]

    def subtree_filter(self, ft: Callable[["NotteNode"], bool]) -> "NotteNode | None":
        def inner(node: NotteNode) -> NotteNode | None:
            children = node.children
            if not ft(node):
                return None

            filtered_children: list[NotteNode] = []
            for child in children:
                filtered_child = inner(child)
                if filtered_child is not None:
                    filtered_children.append(filtered_child)
            updated_node = copy.deepcopy(node)
            updated_node.children = filtered_children
            return updated_node

        return inner(self)


class A11yNode(TypedDict, total=False):
    # from the a11y tree
    role: Required[str]
    name: Required[str]
    children: list["A11yNode"]
    url: str
    # added by the tree processing
    children_roles_count: dict[str, int]
    group_role: str
    group_roles: list[str]
    markdown: str
    # added by the notte processing
    id: str
    path: str  # url:parent-path:role:name
    # stuff for the action listing
    modal: bool
    required: bool
    description: str
    visible: bool
    selected: bool
    checked: bool
    enabled: bool


@dataclass
class A11yTree:
    raw: A11yNode
    simple: A11yNode
