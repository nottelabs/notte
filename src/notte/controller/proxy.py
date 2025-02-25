from notte.actions.base import ExecutableAction
from notte.controller.actions import (
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
from notte.errors.actions import InvalidActionError, MoreThanOneParameterActionError


class NotteActionProxy:
    @staticmethod
    def forward_special(action: ExecutableAction) -> BrowserAction:
        params = action.params_values
        match action.id:
            case BrowserActionId.GOTO.value:
                if len(params) != 1:
                    raise MoreThanOneParameterActionError(action.id, len(params))
                return GotoAction(url=params[0].value)
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
                return CompletionAction(
                    success=bool(params[0].value),
                    answer=params[1].value,
                )
            case BrowserActionId.PRESS_KEY.value:
                if len(params) != 1:
                    raise MoreThanOneParameterActionError(action.id, len(params))
                return PressKeyAction(key=params[0].value)
            case BrowserActionId.SCROLL_UP.value:
                if len(params) != 1:
                    raise MoreThanOneParameterActionError(action.id, len(params))
                return ScrollUpAction(amount=int(params[0].value))
            case BrowserActionId.SCROLL_DOWN.value:
                return ScrollDownAction(amount=int(action.params[0].values[0]))
            case BrowserActionId.WAIT.value:
                if len(params) != 1:
                    raise MoreThanOneParameterActionError(action.id, len(params))
                return WaitAction(time_ms=int(params[0].value))
            case BrowserActionId.GOTO_NEW_TAB.value:
                if len(params) != 1:
                    raise MoreThanOneParameterActionError(action.id, len(params))
                return GotoNewTabAction(url=params[0].value)
            case BrowserActionId.SWITCH_TAB.value:
                if len(params) != 1:
                    raise MoreThanOneParameterActionError(action.id, len(params))
                return SwitchTabAction(tab_index=int(params[0].value))
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
        if len(action.params_values) != 1:
            raise MoreThanOneParameterActionError(action.id, len(action.params_values))
        value: str = action.params_values[0].value
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
            case "button" | "link":
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
                return SelectDropdownOptionAction(
                    id=action.id,
                    option_id=action.node.id,
                    selector=action.node.computed_attributes.selectors,
                    option_selector=action.node.computed_attributes.selectors,
                    text_label=action.node.text,
                    press_enter=action.press_enter,
                )
            case "input":
                return NotteActionProxy.forward_parameter_action(action)
            case "special":
                return NotteActionProxy.forward_special(action)
            case _:
                raise InvalidActionError(action.id, f"unknown action role: {action.role} with id: {action.id}")
