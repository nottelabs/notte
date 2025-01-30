from dataclasses import dataclass, field
from typing import Literal

from notte.browser.dom_tree import ResolvedLocator
from notte.controller.actions import BrowserActionId
from notte.errors.actions import InvalidActionError, MoreThanOneParameterActionError


@dataclass
class ActionParameter:
    name: str
    type: str
    default: str | None = None
    values: list[str] = field(default_factory=list)

    def description(self) -> str:
        base = f"{self.name}: {self.type}"
        if len(self.values) > 0:
            base += f" = [{', '.join(self.values)}]"
        return base


@dataclass
class ActionParameterValue:
    parameter_name: str
    value: str


ActionStatus = Literal["valid", "failed", "excluded"]
ActionRole = Literal["link", "button", "input", "special", "image", "other"]


@dataclass
class CachedAction:
    status: ActionStatus
    description: str
    category: str
    code: str | None
    params: list[ActionParameter] = field(default_factory=list)


@dataclass
class PossibleAction:
    id: str
    description: str
    category: str
    params: list[ActionParameter] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.check_params()

    @property
    def role(self, raise_error: bool = False) -> ActionRole:
        match self.id[0]:
            case "L":
                return "link"
            case "B":
                return "button"
            case "I":
                return "input"
            case "F":
                raise NotImplementedError("Image actions are not supported")
            case "S":
                return "special"
            case _:
                if raise_error:
                    raise InvalidActionError(
                        self.id, f"First ID character must be one of {ActionRole} but got {self.id[0]}"
                    )
                return "other"

    def check_params(self) -> None:
        if self.role == "input":
            if len(self.params) != 1:
                raise MoreThanOneParameterActionError(self.id, len(self.params))


@dataclass
@dataclass
class Action(PossibleAction):
    status: ActionStatus = "valid"

    def __post_init__(self):
        self.check_params()

    def markdown(self) -> str:
        return self.description

    def embedding_description(self) -> str:
        return self.role + " " + self.description


@dataclass
class ExecutableAction(Action):
    locator: ResolvedLocator | None = None
    params_values: list[ActionParameterValue] = field(default_factory=list)
    code: str | None = None


@dataclass
class SpecialAction(Action):
    """
    Special actions are actions that are always available and are not related to the current page.

    GOTO: Go to a specific URL
    SCRAPE: Extract Data page data
    SCREENSHOT: Take a screenshot of the current page
    BACK: Go to the previous page
    FORWARD: Go to the next page
    WAIT: Wait for a specific amount of time (in seconds)
    TERMINATE: Terminate the current session
    OPEN_NEW_TAB: Open a new tab
    PRESS_KEY: Press a specific key
    CLICK_ELEMENT: Click on a specific element
    TYPE_TEXT: Type text into a specific element
    SELECT_OPTION: Select an option from a dropdown
    SCROLL_TO_ELEMENT: Scroll to a specific element
    """

    id: BrowserActionId
    description: str = "Special action"
    category: str = "Special Browser Actions"

    @staticmethod
    def is_special(action_id: str) -> bool:
        return action_id in BrowserActionId.__members__.values()

    def __post_init__(self):
        if not SpecialAction.is_special(self.id):
            raise InvalidActionError(self.id, f"Special actions ID must be one of {BrowserActionId} but got {self.id}")

    @staticmethod
    def goto() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.GOTO,
            description="Go to a specific URL",
            category="Special Browser Actions",
            params=[
                ActionParameter(name="url", type="string", default=None),
            ],
        )

    @staticmethod
    def scrape() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.SCRAPE,
            description="Scrape data from the current page",
            category="Special Browser Actions",
        )

    @staticmethod
    def screenshot() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.SCREENSHOT,
            description="Take a screenshot of the current page",
            category="Special Browser Actions",
        )

    @staticmethod
    def go_back() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.GO_BACK,
            description="Go to the previous page",
            category="Special Browser Actions",
        )

    @staticmethod
    def go_forward() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.GO_FORWARD,
            description="Go to the next page",
            category="Special Browser Actions",
        )

    @staticmethod
    def reload() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.RELOAD,
            description="Refresh the current page",
            category="Special Browser Actions",
        )

    @staticmethod
    def wait() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.WAIT,
            description="Wait for a specific amount of time (in ms)",
            category="Special Browser Actions",
            params=[
                ActionParameter(name="time_ms", type="int", default=None),
            ],
        )

    @staticmethod
    def terminate() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.TERMINATE,
            description="Terminate the current session",
            category="Special Browser Actions",
        )

    @staticmethod
    def press_key() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.PRESS_KEY,
            description="Press a specific key",
            category="Special Browser Actions",
            params=[
                ActionParameter(name="key", type="string", default=None),
            ],
        )

    @staticmethod
    def scroll_up() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.SCROLL_UP,
            description="Scroll up",
            category="Special Browser Actions",
            params=[
                ActionParameter(name="amount", type="int", default=None),
            ],
        )

    @staticmethod
    def scroll_down() -> "SpecialAction":
        return SpecialAction(
            id=BrowserActionId.SCROLL_DOWN,
            description="Scroll down",
            category="Special Browser Actions",
            params=[
                ActionParameter(name="amount", type="int", default=None),
            ],
        )

    @staticmethod
    def list() -> list["SpecialAction"]:
        return [
            SpecialAction.goto(),
            SpecialAction.scrape(),
            SpecialAction.screenshot(),
            SpecialAction.go_back(),
            SpecialAction.go_forward(),
            SpecialAction.reload(),
            SpecialAction.wait(),
            SpecialAction.terminate(),
            SpecialAction.press_key(),
            SpecialAction.scroll_up(),
            SpecialAction.scroll_down(),
        ]
