import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Required, TypedDict

from typing_extensions import override


class NodeCategory(Enum):
    STRUCTURAL = "structural"
    DATA_DISPLAY = "data_display"
    TEXT = "text"
    INTERACTION = "interaction"
    TABLE = "table"
    LIST = "list"
    OTHER = "other"
    CODE = "code"
    TREE = "tree"
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
                    "menuitem",
                    "slider",
                    "switch",
                    "menuitem",
                    "menuitemcheckbox",
                    "menuitemradio",
                }
            case NodeCategory.TEXT.value:
                roles = {
                    "text",
                    "heading",
                    "paragraph",
                    "blockquote",
                    "caption",
                    "contentinfo",
                    "definition",
                    "emphasis",
                    "log",
                    "note",
                    "status",
                    "strong",
                    "subscript",
                    "superscript",
                    "term",
                    "time",
                    "LineBreak",
                }
            case NodeCategory.LIST.value:
                roles = {
                    "list",
                    "listitem",
                    "listmarker",
                }
            case NodeCategory.TABLE.value:
                roles = {
                    "table",
                    "row",
                    "column",
                    "cell",
                    "columnheader",
                    "grid",
                    "gridcell",
                    "rowgroup",
                    "rowheader",
                }
            case NodeCategory.OTHER.value:
                roles = {
                    "complementary",
                    "deletion",
                    "figure",
                    "img",
                    "insertion",
                    "marquee",
                    "meter",
                    "presentation",
                    "progressbar",
                    "scrollbar",
                    "separator",
                    "spinbutton",
                    "timer",
                    "Iframe",
                }
            case NodeCategory.STRUCTURAL.value:
                roles = {
                    "group",
                    "generic",
                    "none",
                    "application",
                    "main",
                    "WebArea",
                }
            case NodeCategory.DATA_DISPLAY.value:
                roles = {
                    "alert",
                    "alertdialog",
                    "article",
                    "banner",
                    "directory",
                    "document",
                    "dialog",
                    "feed",
                    "navigation",
                    "menubar",
                    "radiogroup",
                    "region",
                    "search",
                    "tablist",
                    "tabpanel",
                    "toolbar",
                    "tooltip",
                    "form",
                    "menu",
                }
            case NodeCategory.CODE.value:
                roles = {"code", "math"}
            case NodeCategory.TREE.value:
                roles = {"tree", "treegrid", "treeitem"}
            case NodeCategory.PARAMETERS.value:
                roles = {"option"}
            case _:
                raise ValueError(f"No roles for category {self}")
        if add_group_role:
            roles.update(["group", "generic", "none"])
        return roles


class NodeRole(Enum):
    # structural
    APPLICATION = "application"
    GENERIC = "generic"
    GROUP = "group"
    MAIN = "main"
    NONE = "none"
    WEBAREA = "WebArea"

    # Data display
    ALERT = "alert"
    ALERTDIALOG = "alertdialog"
    ARTICLE = "article"
    BANNER = "banner"
    DIRECTORY = "directory"
    DOCUMENT = "document"
    DIALOG = "dialog"
    FEED = "feed"
    NAVIGATION = "navigation"
    MENUBAR = "menubar"
    RADIOGROUP = "radiogroup"
    REGION = "region"
    SEARCH = "search"
    TABLIST = "tablist"
    TABPANEL = "tabpanel"
    TOOLBAR = "toolbar"
    TOOLTIP = "tooltip"
    FORM = "form"
    MENU = "menu"

    # text
    TEXT = "text"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    BLOCKQUOTE = "blockquote"
    CAPTION = "caption"
    CONTENTINFO = "contentinfo"
    DEFINITION = "definition"
    EMPHASIS = "emphasis"
    LOG = "log"
    NOTE = "note"
    STATUS = "status"
    STRONG = "strong"
    SUBSCRIPT = "subscript"
    SUPERSCRIPT = "superscript"
    TERM = "term"
    TIME = "time"
    LINEBREAK = "LineBreak"

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
    MENUITEM = "menuitem"
    MENUITEMCHECKBOX = "menuitemcheckbox"
    MENUITEMRADIO = "menuitemradio"
    SLIDER = "slider"
    SWITCH = "switch"

    # parameters
    OPTION = "option"

    # table
    TABLE = "table"
    ROW = "row"
    COLUMN = "column"
    CELL = "cell"
    COLUMNHEADER = "columnheader"
    GRID = "grid"
    GRIDCELL = "gridcell"
    ROWGROUP = "rowgroup"
    ROWHEADER = "rowheader"

    # list
    LIST = "list"
    LISTITEM = "listitem"
    LISTMARKER = "listmarker"

    # CODE
    CODE = "code"
    MATH = "math"

    # OTHER
    IFRAME = "Iframe"
    COMPLEMENTARY = "complementary"
    DELETION = "deletion"
    FIGURE = "figure"
    IMG = "img"
    INSERTION = "insertion"
    MARQUEE = "marquee"
    METER = "meter"
    PRESENTATION = "presentation"
    PROGRESSBAR = "progressbar"
    SCROLLBAR = "scrollbar"
    SEPARATOR = "separator"
    SPINBUTTON = "spinbutton"
    TIMER = "timer"

    # TREE
    TREE = "tree"
    TREEGRID = "treegrid"
    TREEITEM = "treeitem"

    @staticmethod
    def from_value(value: str) -> "NodeRole | str":
        if value.upper() in NodeRole.__members__:
            return NodeRole[value.upper()]
        return value

    def short_id(self) -> str | None:
        match self.value:
            case NodeRole.LINK.value:
                return "L"
            case (
                NodeRole.BUTTON.value
                | NodeRole.TAB.value
                | NodeRole.MENUITEM.value
                | NodeRole.RADIO.value
                | NodeRole.CHECKBOX.value
                | NodeRole.MENUITEMCHECKBOX.value
                | NodeRole.MENUITEMRADIO.value
                | NodeRole.SWITCH.value
            ):
                return "B"
            case (
                NodeRole.COMBOBOX.value
                | NodeRole.TEXTBOX.value
                | NodeRole.SEARCHBOX.value
                | NodeRole.LISTBOX.value
                | NodeRole.CHECKBOX.value
                | NodeRole.RADIO.value
                | NodeRole.SLIDER.value
            ):
                return "I"
            case _:
                return None

    def category(self) -> NodeCategory:
        match self.value:
            case (
                NodeRole.TEXT.value
                | NodeRole.HEADING.value
                | NodeRole.PARAGRAPH.value
                | NodeRole.BLOCKQUOTE.value
                | NodeRole.CAPTION.value
                | NodeRole.CONTENTINFO.value
                | NodeRole.DEFINITION.value
                | NodeRole.EMPHASIS.value
                | NodeRole.LOG.value
                | NodeRole.NOTE.value
                | NodeRole.STATUS.value
                | NodeRole.STRONG.value
                | NodeRole.SUBSCRIPT.value
                | NodeRole.SUPERSCRIPT.value
                | NodeRole.TERM.value
                | NodeRole.TIME.value
                | NodeRole.LINEBREAK.value
            ):
                return NodeCategory.TEXT
            case NodeRole.OPTION.value:
                return NodeCategory.PARAMETERS
            case (
                NodeRole.WEBAREA.value
                | NodeRole.GROUP.value
                | NodeRole.GENERIC.value
                | NodeRole.NONE.value
                | NodeRole.APPLICATION.value
                | NodeRole.MAIN.value
            ):
                return NodeCategory.STRUCTURAL
            case (
                NodeRole.ALERT.value
                | NodeRole.ALERTDIALOG.value
                | NodeRole.ARTICLE.value
                | NodeRole.BANNER.value
                | NodeRole.DIRECTORY.value
                | NodeRole.DOCUMENT.value
                | NodeRole.DIALOG.value
                | NodeRole.FEED.value
                | NodeRole.NAVIGATION.value
                | NodeRole.MENUBAR.value
                | NodeRole.RADIOGROUP.value
                | NodeRole.REGION.value
                | NodeRole.SEARCH.value
                | NodeRole.TABLIST.value
                | NodeRole.TABPANEL.value
                | NodeRole.TOOLBAR.value
                | NodeRole.TOOLTIP.value
                | NodeRole.FORM.value
                | NodeRole.MENU.value
            ):
                return NodeCategory.DATA_DISPLAY
            case NodeRole.LIST.value | NodeRole.LISTITEM.value | NodeRole.LISTMARKER.value:
                return NodeCategory.LIST
            case (
                NodeRole.TABLE.value
                | NodeRole.ROW.value
                | NodeRole.COLUMN.value
                | NodeRole.CELL.value
                | NodeRole.COLUMNHEADER.value
                | NodeRole.GRID.value
                | NodeRole.GRIDCELL.value
                | NodeRole.ROWGROUP.value
                | NodeRole.ROWHEADER.value
            ):
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
                | NodeRole.MENUITEM.value
                | NodeRole.MENUITEMCHECKBOX.value
                | NodeRole.MENUITEMRADIO.value
                | NodeRole.SLIDER.value
                | NodeRole.SWITCH.value
            ):
                return NodeCategory.INTERACTION
            case NodeRole.CODE.value | NodeRole.MATH.value:
                return NodeCategory.CODE
            case NodeRole.TREE.value | NodeRole.TREEGRID.value | NodeRole.TREEITEM.value:
                return NodeCategory.TREE
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
    children: list["NotteNode"] = field(default_factory=list)
    attributes_pre: NodeAttributesPre = field(default_factory=NodeAttributesPre)
    attributes_post: NotteAttributesPost | None = None
    subtree_ids: list[str] = field(init=False, default_factory=list)
    _subtree_chars: int = -1  # length of formatted text for this node+children
    _chars: int = -1  # length of the unique tree from root to this node only + children
    _path: list[int] = field(default_factory=list)  # path to this node from root

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
        if self.id is None:
            return False
        return self.role.category().value == NodeCategory.INTERACTION.value

    def flatten(self, only_interaction: bool = False) -> list["NotteNode"]:
        base: list["NotteNode"] = [] if only_interaction and not self.is_interaction() else [self]
        return base + [node for child in self.children for node in child.flatten(only_interaction)]

    def interaction_nodes(self) -> list["InteractionNode"]:
        inodes = self.flatten(only_interaction=True)
        return [InteractionNode(**{k: v for k, v in inode.__dict__.items() if k != "subtree_ids"}) for inode in inodes]

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

    @override
    def __hash__(self) -> int:
        return hash((self.id, self.role, self.text))


class InteractionNode(NotteNode):
    id: str  # type: ignore

    def __post_init__(self) -> None:
        if self.id is None:
            raise ValueError("InteractionNode must have a valid non-None id")
        super().__post_init__()


class A11yNode(TypedDict, total=False):
    # from the a11y tree
    role: Required[str]
    name: Required[str]
    children: list["A11yNode"]
    url: str
    # added by the tree processing
    nb_pruned_children: int
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
