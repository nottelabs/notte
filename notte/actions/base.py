from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from notte.browser.node_type import NotteNode


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
ActionRole = Literal["link", "button", "input", "other"]


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
            case _:
                if raise_error:
                    raise ValueError(f"Invalid action ID: {self.id}. Must be one of {ActionRole}")
                return "other"

    def check_params(self) -> None:
        if self.role == "input":
            if len(self.params) != 1:
                raise ValueError(
                    (
                        "Input actions must have exactly one parameter  but"
                        f" '`{self.id}`: `{self.description}`' has {len(self.params)}"
                    )
                )


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
    node: NotteNode | None = None
    params_values: list[ActionParameterValue] = field(default_factory=list)
    code: str | None = None


class SpecialActionId(StrEnum):
    GOTO = "S1"
    SCRAPE = "S2"
    SCREENSHOT = "S3"
    BACK = "S4"
    FORWARD = "S5"
    REFRESH = "S6"
    WAIT = "S7"
    TERMINATE = "S8"


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
    """

    id: str
    description: str = "Special action"
    category: str = "Special Browser Actions"

    @staticmethod
    def is_special(action_id: str) -> bool:
        return action_id in SpecialActionId.__members__.values()

    def __post_init__(self):
        if not SpecialAction.is_special(self.id):
            raise ValueError(f"Invalid special action ID: {self.id}. Must be one of {SpecialActionId}")

    @staticmethod
    def goto() -> "SpecialAction":
        return SpecialAction(
            id=SpecialActionId.GOTO,
            description="Go to a specific URL",
            category="Special Browser Actions",
            params=[
                ActionParameter(name="url", type="string", default=None),
            ],
        )

    @staticmethod
    def scrape() -> "SpecialAction":
        return SpecialAction(
            id=SpecialActionId.SCRAPE,
            description="Scrape data from the current page",
            category="Special Browser Actions",
        )

    @staticmethod
    def screenshot() -> "SpecialAction":
        return SpecialAction(
            id=SpecialActionId.SCREENSHOT,
            description="Take a screenshot of the current page",
            category="Special Browser Actions",
        )

    @staticmethod
    def back() -> "SpecialAction":
        return SpecialAction(
            id=SpecialActionId.BACK,
            description="Go to the previous page",
            category="Special Browser Actions",
        )

    @staticmethod
    def forward() -> "SpecialAction":
        return SpecialAction(
            id=SpecialActionId.FORWARD,
            description="Go to the next page",
            category="Special Browser Actions",
        )

    @staticmethod
    def refresh() -> "SpecialAction":
        return SpecialAction(
            id=SpecialActionId.REFRESH,
            description="Refresh the current page",
            category="Special Browser Actions",
        )

    @staticmethod
    def wait() -> "SpecialAction":
        return SpecialAction(
            id=SpecialActionId.WAIT,
            description="Wait for a specific amount of time (in seconds)",
            category="Special Browser Actions",
        )

    @staticmethod
    def terminate() -> "SpecialAction":
        return SpecialAction(
            id=SpecialActionId.TERMINATE,
            description="Terminate the current session",
            category="Special Browser Actions",
        )

    @staticmethod
    def list() -> list["SpecialAction"]:
        return [
            SpecialAction.goto(),
            SpecialAction.scrape(),
            SpecialAction.screenshot(),
            SpecialAction.back(),
            SpecialAction.forward(),
            SpecialAction.refresh(),
            SpecialAction.wait(),
            SpecialAction.terminate(),
        ]
