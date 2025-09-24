from collections.abc import Sequence
from typing import Literal

from notte_core.actions import (
    ActionParameter,
    CheckAction,
    ClickAction,
    FillAction,
    InteractionAction,
    SelectDropdownOptionAction,
)
from notte_core.browser.dom_tree import DomNode, InteractionDomNode
from notte_core.errors.actions import InputActionShouldHaveOneParameterError, InvalidActionError
from pydantic import BaseModel

ActionStatus = Literal["valid", "failed", "excluded"]
AllActionStatus = ActionStatus | Literal["all"]
ActionRole = Literal["link", "button", "input", "special", "image", "option", "misc", "other"]
AllActionRole = ActionRole | Literal["all"]


class NotteActionProxy:
    @staticmethod
    def _parse_boolean(value: str) -> bool:
        if value.lower() in ("true", "1", "yes", "on"):
            return True
        elif value.lower() in ("false", "0", "no", "off"):
            return False
        else:
            raise InvalidActionError("unknown", f"Invalid boolean value: {value}")

    @staticmethod
    def get_role(id: str, raise_error: bool = False) -> ActionRole:
        if not id:
            if raise_error:
                raise InvalidActionError(id, "Action ID cannot be empty")
            return "other"
        match id[0]:
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
            case _:
                if raise_error:
                    raise InvalidActionError(id, f"First ID character must be one of {ActionRole} but got {id[0]}")
                return "other"

    @staticmethod
    def forward_parameter_action(
        node: DomNode, action_id: str, value: str | None, press_enter: bool = False
    ) -> InteractionAction:
        if value is None:
            raise InputActionShouldHaveOneParameterError(action_id)
        role = NotteActionProxy.get_role(action_id)
        match (role, node.get_role_str(), node.computed_attributes.is_editable):
            case ("input", "textbox", _) | (_, _, True):
                return FillAction(
                    id=action_id,
                    value=value,
                    press_enter=press_enter,
                    selector=node.computed_attributes.selectors,
                    text_label=node.inner_text(),
                )
            case ("input", "checkbox", _):
                return CheckAction(
                    id=action_id,
                    value=NotteActionProxy._parse_boolean(value),
                    press_enter=press_enter,
                    selector=node.computed_attributes.selectors,
                    text_label=node.text,
                )
            case ("input", "combobox", _):
                return SelectDropdownOptionAction(
                    id=action_id,
                    value=value,
                    press_enter=press_enter,
                    selector=node.computed_attributes.selectors,
                    text_label=node.text,
                )
            case ("input", _, _):
                return FillAction(
                    id=action_id,
                    value=value,
                    press_enter=press_enter,
                    selector=node.computed_attributes.selectors,
                    text_label=node.inner_text(),
                )
            case _:
                raise InvalidActionError(action_id, f"unknown action type: {action_id[0]}")

    @staticmethod
    def forward(node: DomNode, action_id: str, value: str | None, press_enter: bool | None = None) -> InteractionAction:
        match NotteActionProxy.get_role(action_id):
            case "button" | "link" | "image" | "misc":
                return ClickAction(
                    id=action_id,
                    text_label=node.text,
                    selector=node.computed_attributes.selectors,
                    press_enter=press_enter,
                )
            case "option":
                # TODO: fix gufo
                return SelectDropdownOptionAction(
                    id=action_id,
                    value=node.id or "",
                    selector=node.computed_attributes.selectors,
                    text_label=node.text,
                    press_enter=press_enter,
                )
            case "input":
                return NotteActionProxy.forward_parameter_action(node, action_id, value)
            case _:
                raise InvalidActionError(action_id, f"unknown action role: {action_id[0]} with id: {action_id}")


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
        value = None if self.param is None else "<sample_value>"
        action = NotteActionProxy.forward(node, self.id, value)
        action.description = self.description
        action.category = self.category
        action.param = self.param
        return action


class PossibleActionSpace(BaseModel):
    description: str
    actions: Sequence[PossibleAction]
