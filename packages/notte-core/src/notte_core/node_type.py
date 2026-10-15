from collections.abc import Mapping
from enum import Enum

from notte_core.logging import logger


class NodeType(Enum):
    TEXT = "text"
    INTERACTION = "interaction"
    OTHER = "other"


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

    @staticmethod
    def from_element(tag_name: str, attributes: Mapping[str, str]) -> "NodeRole | str":
        """The role of an HTML element: its `role` attribute if set, else the implicit role of its tag.

        A `role` attribute that is not a `NodeRole` is returned as is (a string).
        """
        explicit_role = attributes.get("role")
        if explicit_role:
            return NodeRole.from_value(explicit_role)
        if len(tag_name) == 0:
            return NodeRole.NONE
        tag = tag_name.lower()
        if tag == "input":
            return _INPUT_TYPE_ROLES.get(attributes.get("type", "text").lower(), NodeRole.TEXTBOX)
        role = _TAG_ROLES.get(tag)
        if role is not None:
            return role
        # custom elements, e.g. <my-menu-item>
        clean_tag = tag.replace("-", "").replace("_", "")
        for role in _CUSTOM_ELEMENT_ROLES:
            if role.value in clean_tag:
                return role
        if "popup" in clean_tag:
            return NodeRole.MENULISTPOPUP
        return NodeRole.GENERIC

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

    def is_interactive(self) -> bool:
        return self in _INTERACTIVE_ROLES


# implicit role of an <input>, by its `type` (default: textbox)
_INPUT_TYPE_ROLES: dict[str, NodeRole] = {
    # TODO: could create a special type for submit/reset
    "button": NodeRole.BUTTON,
    "submit": NodeRole.BUTTON,
    "reset": NodeRole.BUTTON,
    "radio": NodeRole.RADIO,
    "checkbox": NodeRole.CHECKBOX,
    "search": NodeRole.SEARCHBOX,
}

# implicit role of an element, by its (lowercase) tag name
_TAG_ROLES: dict[str, NodeRole] = {
    # structural elements
    "body": NodeRole.WEBAREA,
    "nav": NodeRole.NAVIGATION,
    "main": NodeRole.MAIN,
    "header": NodeRole.BANNER,
    "footer": NodeRole.CONTENTINFO,
    "aside": NodeRole.COMPLEMENTARY,
    "section": NodeRole.ARTICLE,
    "article": NodeRole.ARTICLE,
    "div": NodeRole.GROUP,
    # interactive elements (<input> is handled separately)
    "a": NodeRole.LINK,
    "button": NodeRole.BUTTON,
    "select": NodeRole.COMBOBOX,
    "textarea": NodeRole.TEXTBOX,
    "option": NodeRole.OPTION,
    # text elements
    **{f"h{level}": NodeRole.HEADING for level in range(1, 7)},
    "p": NodeRole.PARAGRAPH,
    **{tag: NodeRole.TEXT for tag in ("span", "strong", "em", "small", "bdi", "i")},
    "label": NodeRole.LABELTEXT,
    "blockquote": NodeRole.BLOCKQUOTE,
    "code": NodeRole.CODE,
    "pre": NodeRole.CODE,
    "time": NodeRole.TIME,
    "br": NodeRole.LINEBREAK,
    # list elements
    "ul": NodeRole.LIST,
    "ol": NodeRole.LIST,
    "dl": NodeRole.LIST,
    "li": NodeRole.LISTITEM,
    "dt": NodeRole.LISTITEM,
    "dd": NodeRole.LISTITEM,
    # table elements
    "table": NodeRole.TABLE,
    "tr": NodeRole.ROW,
    "td": NodeRole.CELL,
    "th": NodeRole.COLUMNHEADER,
    "thead": NodeRole.ROWGROUP,
    "tbody": NodeRole.ROWGROUP,
    "tfoot": NodeRole.ROWGROUP,
    # media elements
    "img": NodeRole.IMG,
    "figure": NodeRole.FIGURE,
    "iframe": NodeRole.IFRAME,
    # form elements
    "form": NodeRole.FORM,
    "fieldset": NodeRole.GROUP,
    "dialog": NodeRole.DIALOG,
    "progress": NodeRole.PROGRESSBAR,
    "meter": NodeRole.METER,
    # menu elements
    "menu": NodeRole.MENU,
    "menuitem": NodeRole.MENUITEM,
    "hr": NodeRole.SEPARATOR,
}

# roles looked for (in this order) in the tag name of the other elements, without '-' and '_'
_CUSTOM_ELEMENT_ROLES: tuple[NodeRole, ...] = (
    NodeRole.MENUITEMCHECKBOX,
    NodeRole.MENUITEMRADIO,
    NodeRole.MENUITEM,
    NodeRole.MENU,
    NodeRole.DIALOG,
)


_INTERACTIVE_ROLES = frozenset(
    {
        NodeRole.BUTTON,
        NodeRole.LINK,
        NodeRole.COMBOBOX,
        NodeRole.TEXTBOX,
        NodeRole.CHECKBOX,
        NodeRole.SEARCHBOX,
        NodeRole.RADIO,
        NodeRole.TAB,
        NodeRole.LISTBOX,
        NodeRole.MENUITEM,
        NodeRole.MENUITEMCHECKBOX,
        NodeRole.MENUITEMRADIO,
        NodeRole.SLIDER,
        NodeRole.SWITCH,
        NodeRole.OPTION,
    }
)
