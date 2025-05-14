from collections.abc import Sequence
from typing import Literal

from notte_core.actions.percieved import ActionParameter
from notte_core.errors.actions import MoreThanOneParameterActionError
from pydantic import BaseModel, Field

ActionStatus = Literal["valid", "failed", "excluded"]


class CachedAction(BaseModel):
    status: ActionStatus
    description: str
    category: str
    code: str | None
    params: list[ActionParameter] = Field(default_factory=list)


# generic action that can be parametrized
class PossibleAction(BaseModel):
    id: str
    description: str
    category: str
    params: list[ActionParameter] = Field(default_factory=list)

    def __post_init__(self) -> None:
        self.check_params()

    def check_params(self) -> None:
        if self.id.startswith("I"):
            if len(self.params) != 1:
                raise MoreThanOneParameterActionError(self.id, len(self.params))


class PossibleActionSpace(BaseModel):
    description: str
    actions: Sequence[PossibleAction]
