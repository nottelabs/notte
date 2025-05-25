from notte_core.actions.base import ExecutableAction
from notte_core.browser.dom_tree import DomNode
from notte_core.controller.actions import (
    CheckAction,
    ClickAction,
    FillAction,
    InteractionAction,
    SelectDropdownOptionAction,
)
from notte_core.credentials.types import get_str_value
from notte_core.errors.actions import InvalidActionError, MoreThanOneParameterActionError


class NotteActionProxy:
    @staticmethod
    def forward_parameter_action(action: ExecutableAction, node: DomNode) -> InteractionAction:
        if action.value is None:
            raise MoreThanOneParameterActionError(action.id, 0)
        value: str = get_str_value(action.value.value)
        match (action.role, node.get_role_str(), node.computed_attributes.is_editable):
            case ("input", "textbox", _) | (_, _, True):
                return FillAction(
                    id=action.id,
                    value=value,
                    press_enter=action.press_enter,
                    selector=action.selector,
                    text_label=node.inner_text(),
                )
            case ("input", "checkbox", _):
                return CheckAction(
                    id=action.id,
                    value=bool(value),
                    press_enter=action.press_enter,
                    selector=action.selector,
                    text_label=node.text,
                )
            case ("input", "combobox", _):
                return SelectDropdownOptionAction(
                    id=action.id,
                    value=value,
                    press_enter=action.press_enter,
                    selector=action.selector,
                    text_label=node.text,
                )
            case ("input", _, _):
                return FillAction(
                    id=action.id,
                    value=value,
                    press_enter=action.press_enter,
                    selector=action.selector,
                    text_label=node.inner_text(),
                )
            case _:
                raise InvalidActionError(action.id, f"unknown action type: {action.id[0]}")

    @staticmethod
    def forward(action: ExecutableAction, node: DomNode) -> InteractionAction:
        match action.role:
            case "button" | "link" | "image" | "misc":
                return ClickAction(
                    id=action.id,
                    text_label=node.text,
                    selector=node.computed_attributes.selectors,
                    press_enter=action.press_enter,
                )
            case "option":
                # TODO: fix gufo
                return SelectDropdownOptionAction(
                    id=action.id,
                    value=node.id or "",
                    selector=node.computed_attributes.selectors,
                    text_label=node.text,
                    press_enter=action.press_enter,
                )
            case "input":
                return NotteActionProxy.forward_parameter_action(action, node)
            case _:
                raise InvalidActionError(action.id, f"unknown action role: {action.role} with id: {action.id}")
