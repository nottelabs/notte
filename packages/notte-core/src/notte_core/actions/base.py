from typing import Literal

from pydantic import BaseModel
from typing_extensions import override

from notte_core.browser.dom_tree import DomNode
from notte_core.controller.actions import ActionParameter, ActionRole, ActionStatus, BaseAction, InteractionAction
from notte_core.credentials.types import ValueWithPlaceholder
from notte_core.errors.actions import InvalidActionError, MoreThanOneParameterActionError


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
    type: Literal["executable"] = "executable"  # pyright: ignore [reportIncompatibleVariableOverride]
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
    type: Literal["executable"] = "executable"  # pyright: ignore [reportIncompatibleVariableOverride]
    category: str = "Executable Actions"
    description: str = "Executable action"
    value: ActionParameterValue | None = None
    node: DomNode | None = None
