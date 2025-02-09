from notte.actions.base import ExecutableAction
from notte.controller.actions import (
    BaseAction,
    BrowserAction,
    BrowserActionId,
    CheckAction,
    ClickAction,
    CompletionAction,
    FillAction,
    GoBackAction,
    GoForwardAction,
    GotoAction,
    InteractionAction,
    PressKeyAction,
    ReloadAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    WaitAction,
)
from notte.errors.actions import InvalidActionError, MoreThanOneParameterActionError
from notte.errors.resolution import NodeResolutionAttributeError


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
            case _:
                raise InvalidActionError(
                    action_id=action.id,
                    reason=(
                        f"try executing a special action but '{action.id}' is not a special action. "
                        f"Special actions are {list(BrowserActionId)}"
                    ),
                )

    @staticmethod
    def forward_parameter_action(action: ExecutableAction, enter: bool | None = None) -> InteractionAction:
        if action.locator is None:
            raise NodeResolutionAttributeError(None, "post_attributes")  # type: ignore
        if len(action.params_values) != 1:
            raise MoreThanOneParameterActionError(action.id, len(action.params_values))
        value: str = action.params_values[0].value
        node_role = action.locator.role if isinstance(action.locator.role, str) else action.locator.role.value
        match (action.role, node_role, action.locator.is_editable):
            case (_, _, True) | ("input", "textbox", _):
                return FillAction(id=action.id, selector=action.locator.selector, value=value, press_enter=enter)
            case ("input", "checkbox", _):
                return CheckAction(id=action.id, selector=action.locator.selector, value=bool(value), press_enter=enter)
            case ("input", "combobox", _):
                return SelectDropdownOptionAction(
                    id=action.id, selector=action.locator.selector, value=value, press_enter=enter
                )
            case ("input", _, _):
                return FillAction(id=action.id, selector=action.locator.selector, value=value, press_enter=enter)
            case _:
                raise InvalidActionError(action.id, f"unknown action type: {action.id[0]}")

    @staticmethod
    def forward(action: ExecutableAction, enter: bool | None = None) -> BaseAction:
        match action.role:
            case "button" | "link":
                if action.locator is None:
                    raise InvalidActionError(action.id, "locator is to be able to execute an interaction action")
                return ClickAction(id=action.id, selector=action.locator.selector, press_enter=enter)
            case "input":
                return NotteActionProxy.forward_parameter_action(action, enter=enter)
            case "special":
                return NotteActionProxy.forward_special(action)
            case _:
                raise InvalidActionError(action.id, f"unknown action type: {action.id[0]}")
