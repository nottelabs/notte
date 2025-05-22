from notte_core.actions.base import ExecutableAction
from notte_core.controller.actions import (
    BrowserAction,
    BrowserActionId,
    CheckAction,
    ClickAction,
    CompletionAction,
    FillAction,
    GoBackAction,
    GoForwardAction,
    GotoAction,
    GotoNewTabAction,
    InteractionAction,
    PressKeyAction,
    ReloadAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    SwitchTabAction,
    WaitAction,
)
from notte_core.credentials.types import get_str_value
from notte_core.errors.actions import InvalidActionError, MoreThanOneParameterActionError


class NotteActionProxy:
    @staticmethod
    def forward_special(action: ExecutableAction) -> BrowserAction:
        param = action.value.value if action.value is not None else None
        match action.id:
            case BrowserActionId.GOTO.value:
                if param is None:
                    raise MoreThanOneParameterActionError(action.id, 0)
                return GotoAction(url=get_str_value(param))
            case BrowserActionId.SCRAPE.value:
                return ScrapeAction()
            # case BrowserActionId.SCREENSHOT:
            #     return ScreenshotAction()
            case BrowserActionId.GO_BACK.value:
                return GoBackAction()
            case BrowserActionId.GO_FORWARD.value:
                return GoForwardAction()
            case BrowserActionId.RELOAD.value:
                return ReloadAction()
            case BrowserActionId.COMPLETION.value:
                if param is None:
                    raise MoreThanOneParameterActionError(action.id, 0)
                return CompletionAction(success=bool(param), answer=get_str_value(param))
            case BrowserActionId.PRESS_KEY.value:
                if param is None:
                    raise MoreThanOneParameterActionError(action.id, 0)
                return PressKeyAction(key=get_str_value(param))
            case BrowserActionId.SCROLL_UP.value:
                if param is None:
                    raise MoreThanOneParameterActionError(action.id, 0)
                return ScrollUpAction(amount=int(get_str_value(param)))
            case BrowserActionId.SCROLL_DOWN.value:
                if param is None:
                    raise MoreThanOneParameterActionError(action.id, 0)
                return ScrollDownAction(amount=int(get_str_value(param)))
            case BrowserActionId.WAIT.value:
                if param is None:
                    raise MoreThanOneParameterActionError(action.id, 0)
                return WaitAction(time_ms=int(get_str_value(param)))
            case BrowserActionId.GOTO_NEW_TAB.value:
                if param is None:
                    raise MoreThanOneParameterActionError(action.id, 0)
                return GotoNewTabAction(url=get_str_value(param))
            case BrowserActionId.SWITCH_TAB.value:
                if param is None:
                    raise MoreThanOneParameterActionError(action.id, 0)
                return SwitchTabAction(tab_index=int(get_str_value(param)))
            case _:
                raise InvalidActionError(
                    action_id=action.id,
                    reason=(
                        f"try executing a special action but '{action.id}' is not a special action. "
                        f"Special actions are {list(BrowserActionId)}"
                    ),
                )

    @staticmethod
    def forward_parameter_action(action: ExecutableAction) -> InteractionAction:
        if action.node is None:
            raise InvalidActionError(
                action.id, reason="action.node cannot be None to be able to execute an interaction action"
            )
        if action.value is None:
            raise MoreThanOneParameterActionError(action.id, 0)
        value: str = get_str_value(action.value.value)
        match (action.role, action.node.get_role_str(), action.node.computed_attributes.is_editable):
            case ("input", "textbox", _) | (_, _, True):
                return FillAction(
                    id=action.id,
                    value=value,
                    press_enter=action.press_enter,
                    selector=action.selector,
                    text_label=action.node.inner_text(),
                )
            case ("input", "checkbox", _):
                return CheckAction(
                    id=action.id,
                    value=bool(value),
                    press_enter=action.press_enter,
                    selector=action.selector,
                    text_label=action.node.text,
                )
            case ("input", "combobox", _):
                return SelectDropdownOptionAction(
                    id=action.id,
                    value=value,
                    press_enter=action.press_enter,
                    selector=action.selector,
                    text_label=action.node.text,
                )
            case ("input", _, _):
                return FillAction(
                    id=action.id,
                    value=value,
                    press_enter=action.press_enter,
                    selector=action.selector,
                    text_label=action.node.inner_text(),
                )
            case _:
                raise InvalidActionError(action.id, f"unknown action type: {action.id[0]}")

    @staticmethod
    def forward(action: ExecutableAction) -> InteractionAction | BrowserAction:
        match action.role:
            case "button" | "link" | "image" | "misc":
                if action.node is None:
                    raise InvalidActionError(
                        action.id, "action.node cannot be None to be able to execute an interaction action"
                    )
                return ClickAction(
                    id=action.id,
                    text_label=action.node.text,
                    selector=action.node.computed_attributes.selectors,
                    press_enter=action.press_enter,
                )
            case "option":
                if action.node is None:
                    raise InvalidActionError(
                        action.id, "action.node cannot be None to be able to execute an interaction action"
                    )

                # TODO: fix gufo
                return SelectDropdownOptionAction(
                    id=action.id,
                    value=action.node.id or "",
                    selector=action.node.computed_attributes.selectors,
                    text_label=action.node.text,
                    press_enter=action.press_enter,
                )
            case "input":
                return NotteActionProxy.forward_parameter_action(action)
            case "special":
                return NotteActionProxy.forward_special(action)
            case _:
                raise InvalidActionError(action.id, f"unknown action role: {action.role} with id: {action.id}")
