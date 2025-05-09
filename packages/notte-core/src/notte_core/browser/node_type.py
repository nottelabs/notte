from enum import Enum

from loguru import logger


class NodeType(Enum):
    TEXT = "text"
    INTERACTION = "interaction"
    IMAGE = "image"
    OTHER = "other"


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
    IMAGE = "image"

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
                    "option",
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
                    "DescriptionList",
                    "LabelText",
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
            case NodeCategory.IMAGE.value:
                roles = {"image", "img", "figure"}
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
                    "MenuListPopup",
                    "modal",
                }
            case NodeCategory.CODE.value:
                roles = {"code", "math"}
            case NodeCategory.TREE.value:
                roles = {"tree", "treegrid", "treeitem"}
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
    MENULISTPOPUP = "MenuListPopup"
    MODAL = "modal"

    # text
    TEXT = "text"
    LABELTEXT = "LabelText"
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
    DESCRIPTIONLIST = "DescriptionList"

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

    # IMAGE
    FIGURE = "figure"
    IMG = "img"
    IMAGE = "image"

    # OTHER
    IFRAME = "Iframe"
    COMPLEMENTARY = "complementary"
    DELETION = "deletion"
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

    def short_id(self, force_id: bool = False) -> str | None:
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
            case NodeRole.IMAGE.value | NodeRole.IMG.value | NodeRole.FIGURE.value:
                return "F"
            case NodeRole.OPTION.value:
                return "O"
            case _:
                if force_id:
                    logger.debug(f"No short id for role {self}. Returning 'M' (forced).")
                    return "M"
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
                | NodeRole.DESCRIPTIONLIST.value
                | NodeRole.LABELTEXT.value
            ):
                return NodeCategory.TEXT
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
                | NodeRole.MENULISTPOPUP.value
                | NodeRole.MODAL.value
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
                | NodeRole.OPTION.value
            ):
                return NodeCategory.INTERACTION
            case NodeRole.CODE.value | NodeRole.MATH.value:
                return NodeCategory.CODE
            case NodeRole.TREE.value | NodeRole.TREEGRID.value | NodeRole.TREEITEM.value:
                return NodeCategory.TREE
            case NodeRole.IMAGE.value | NodeRole.FIGURE.value | NodeRole.IMG.value:
                return NodeCategory.IMAGE
            case _:
                return NodeCategory.OTHER
