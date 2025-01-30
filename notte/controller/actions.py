from enum import StrEnum

from pydantic import BaseModel

# ############################################################
# Action enums
# ############################################################


class BrowserActionId(StrEnum):
    # Base actions
    GOTO = "S1"
    SCRAPE = "S2"
    SCREENSHOT = "S3"
    # Tab actions
    GO_BACK = "S4"
    GO_FORWARD = "P5"
    RELOAD = "P6"
    # Press & Scroll actions
    PRESS_KEY = "P7"
    SCROLL_UP = "P8"
    SCROLL_DOWN = "P9"
    # Session actions
    WAIT = "P10"
    TERMINATE = "P11"


class InteractionActionId(StrEnum):
    CLICK = "A1"
    FILL = "A2"
    CHECK = "A3"
    SELECT = "A4"


# ############################################################
# Browser actions models
# ############################################################


class BaseAction(BaseModel):
    """Base model for all actions."""

    id: BrowserActionId | InteractionActionId


class BrowserAction(BaseAction):
    """Base model for special actions that are always available and not related to the current page."""

    id: BrowserActionId


class GotoAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GOTO
    url: str


class ScrapeAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCRAPE
    url: str | None = None


class ScreenshotAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCREENSHOT


class GoBackAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GO_BACK


class GoForwardAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.GO_FORWARD


class ReloadAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.RELOAD


class WaitAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.WAIT
    time_ms: int


class TerminateAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.TERMINATE


class PressKeyAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.PRESS_KEY
    key: str


class ScrollUpAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCROLL_UP
    # amount of pixels to scroll. None for scrolling up one page
    amount: int | None = None


class ScrollDownAction(BrowserAction):
    id: BrowserActionId = BrowserActionId.SCROLL_DOWN
    # amount of pixels to scroll. None for scrolling down one page
    amount: int | None = None


# ############################################################
# Interaction actions models
# ############################################################


class InteractionAction(BaseAction):
    id: InteractionActionId
    selector: str


class ClickAction(InteractionAction):
    id: InteractionActionId = InteractionActionId.CLICK


class FillAction(InteractionAction):
    id: InteractionActionId = InteractionActionId.FILL
    value: str


class CheckAction(InteractionAction):
    id: InteractionActionId = InteractionActionId.CHECK
    value: bool


class SelectAction(InteractionAction):
    id: InteractionActionId = InteractionActionId.SELECT
    value: str
