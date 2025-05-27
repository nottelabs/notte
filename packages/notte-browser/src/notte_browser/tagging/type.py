from collections.abc import Sequence

from notte_core.actions import (
    ActionParameter,
    ActionParameterValue,
    InteractionAction,
    StepAction,
)
from notte_core.browser.dom_tree import InteractionDomNode
from notte_core.errors.actions import InputActionShouldHaveOneParameterError
from pydantic import BaseModel

from notte_browser.resolution import NotteActionProxy


# generic action that can be parametrized
class PossibleAction(BaseModel):
    id: str
    description: str
    category: str
    param: ActionParameter | None = None

    def __post_init__(self) -> None:
        if self.id.startswith("I"):
            if self.param is None:
                raise InputActionShouldHaveOneParameterError(self.id)

    def to_interaction(self, node: InteractionDomNode) -> InteractionAction:
        action = StepAction(
            id=node.id,
            category=self.category,
            description=self.description,
            value=ActionParameterValue(
                name=self.param.name,
                value="<sample_value>",
            )
            if self.param is not None
            else None,
            param=self.param,
        )
        action = NotteActionProxy.forward(action, node=node)
        action.description = self.description
        action.category = self.category
        action.param = self.param
        return action


class PossibleActionSpace(BaseModel):
    description: str
    actions: Sequence[PossibleAction]
