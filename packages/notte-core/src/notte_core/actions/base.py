from typing import Literal

from pydantic import BaseModel, Field
from typing_extensions import override

from notte_core.browser.dom_tree import DomNode
from notte_core.controller.actions import ActionRole, ActionStatus, BaseAction, BrowserActionId, InteractionAction
from notte_core.controller.actions import BrowserAction as _BrowserAction
from notte_core.credentials.types import ValueWithPlaceholder
from notte_core.errors.actions import InvalidActionError, MoreThanOneParameterActionError


class ActionParameter(BaseModel):
    name: str
    type: str
    default: str | None = None
    values: list[str] = Field(default_factory=list)

    def description(self) -> str:
        base = f"{self.name}: {self.type}"
        if len(self.values) > 0:
            base += f" = [{', '.join(self.values)}]"
        return base


class ActionParameterValue(BaseModel):
    name: str
    value: str | ValueWithPlaceholder


class CachedAction(BaseModel):
    status: ActionStatus
    description: str
    category: str
    code: str | None
    param: ActionParameter | None = None


# generic action that can be parametrized
class PossibleAction(BaseModel):
    id: str
    description: str
    category: str
    param: ActionParameter | None = None

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
            case "O":
                return "option"
            case "M":
                return "misc"
            case "F":
                # figure / image
                return "image"
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
            if self.param is None:
                raise MoreThanOneParameterActionError(self.id, 0)


class Action(BaseAction, PossibleAction):
    status: ActionStatus = "valid"
    param: ActionParameter | None = None

    def markdown(self) -> str:
        return self.description

    def embedding_description(self) -> str:
        return self.role + " " + self.description

    @override
    def execution_message(self) -> str:
        # TODO: think about a better message here
        return f"Sucessfully executed: '{self.description}'"


class ExecutableAction(Action, InteractionAction):
    """
    An action that can be executed by the proxy.
    """

    # description is not needed for the proxy
    type: Literal["executable"] = "executable"
    category: str = "Executable Actions"
    description: str = "Executable action"
    value: ActionParameterValue | None = None
    node: DomNode | None = None


class BrowserAction(Action, _BrowserAction):
    """
    Browser actions are actions that are always available and are not related to the current page.

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

    id: BrowserActionId  # type: ignore[type-assignment]
    description: str = "Special action"
    category: str = "Special Browser Actions"

    @staticmethod
    def is_special(action_id: str) -> bool:
        return action_id in BrowserActionId.__members__.values()

    def __post_init__(self):
        if not BrowserAction.is_special(self.id):
            raise InvalidActionError(self.id, f"Special actions ID must be one of {BrowserActionId} but got {self.id}")

    @staticmethod
    def goto() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.GOTO,
            description="Go to a specific URL",
            category="Special Browser Actions",
            param=ActionParameter(name="url", type="string", default=None),
        )

    @staticmethod
    def scrape() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.SCRAPE,
            description="Scrape data from the current page",
            category="Special Browser Actions",
        )

    # @staticmethod
    # def screenshot() -> "BrowserAction":
    #     return BrowserAction(
    #         id=BrowserActionId.SCREENSHOT,
    #         description="Take a screenshot of the current page",
    #         category="Special Browser Actions",
    #     )

    @staticmethod
    def go_back() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.GO_BACK,
            description="Go to the previous page",
            category="Special Browser Actions",
        )

    @staticmethod
    def go_forward() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.GO_FORWARD,
            description="Go to the next page",
            category="Special Browser Actions",
        )

    @staticmethod
    def reload() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.RELOAD,
            description="Refresh the current page",
            category="Special Browser Actions",
        )

    @staticmethod
    def wait() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.WAIT,
            description="Wait for a specific amount of time (in ms)",
            category="Special Browser Actions",
            param=ActionParameter(name="time_ms", type="int", default=None),
        )

    @staticmethod
    def completion() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.COMPLETION,
            description="Terminate the current session",
            category="Special Browser Actions",
        )

    @staticmethod
    def press_key() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.PRESS_KEY,
            description="Press a specific key",
            category="Special Browser Actions",
            param=ActionParameter(name="key", type="string", default=None),
        )

    @staticmethod
    def scroll_up() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.SCROLL_UP,
            description="Scroll up",
            category="Special Browser Actions",
            param=ActionParameter(name="amount", type="int", default=None),
        )

    @staticmethod
    def scroll_down() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.SCROLL_DOWN,
            description="Scroll down",
            category="Special Browser Actions",
            param=ActionParameter(name="amount", type="int", default=None),
        )

    @staticmethod
    def goto_new_tab() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.GOTO_NEW_TAB,
            description="Go to a new tab",
            category="Special Browser Actions",
            param=ActionParameter(name="url", type="string"),
        )

    @staticmethod
    def switch_tab() -> "BrowserAction":
        return BrowserAction(
            id=BrowserActionId.SWITCH_TAB,
            description="Switch to a specific tab",
            category="Special Browser Actions",
            param=ActionParameter(name="tab_index", type="int"),
        )

    @staticmethod
    def list() -> list["BrowserAction"]:
        return [
            BrowserAction.goto(),
            BrowserAction.scrape(),
            BrowserAction.go_back(),
            BrowserAction.go_forward(),
            BrowserAction.reload(),
            BrowserAction.wait(),
            BrowserAction.completion(),
            BrowserAction.press_key(),
            BrowserAction.scroll_up(),
            BrowserAction.scroll_down(),
            BrowserAction.goto_new_tab(),
            BrowserAction.switch_tab(),
            # BrowserAction.screenshot(),
        ]
