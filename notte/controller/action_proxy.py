from notte.actions.base import ExecutableAction
from notte.controller.actions import (
    BaseAction,
    BrowserAction,
    BrowserActionId,
    CheckAction,
    ClickAction,
    FillAction,
    GoBackAction,
    GoForwardAction,
    GotoAction,
    InteractionAction,
    PressKeyAction,
    ReloadAction,
    ScrapeAction,
    ScreenshotAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectAction,
    TerminateAction,
    WaitAction,
)
from notte.errors.actions import InvalidActionError, MoreThanOneParameterActionError
from notte.errors.resolution import NodeResolutionAttributeError


class NotteActionProxy:

    @staticmethod
    def forward_special(action: ExecutableAction) -> BrowserAction:
        match action.id:
            case BrowserActionId.GOTO:
                return GotoAction(url=action.params[0].values[0])
            case BrowserActionId.SCRAPE:
                return ScrapeAction(url=action.params[0].values[0])
            case BrowserActionId.SCREENSHOT:
                return ScreenshotAction()
            case BrowserActionId.GO_BACK:
                return GoBackAction()
            case BrowserActionId.GO_FORWARD:
                return GoForwardAction()
            case BrowserActionId.RELOAD:
                return ReloadAction()
            case BrowserActionId.TERMINATE:
                return TerminateAction()
            case BrowserActionId.PRESS_KEY:
                return PressKeyAction(key=action.params[0].values[0])
            case BrowserActionId.SCROLL_UP:
                return ScrollUpAction(amount=int(action.params[0].values[0]))
            case BrowserActionId.SCROLL_DOWN:
                return ScrollDownAction(amount=int(action.params[0].values[0]))
            case BrowserActionId.WAIT:
                return WaitAction(time_ms=int(action.params[0].values[0]))
            case BrowserActionId.TERMINATE:
                return TerminateAction()
            case _:
                raise InvalidActionError(
                    action_id=action.id,
                    reason=(
                        (
                            f"try executing a special action but '{action.id}' is not a special action. "
                            f"Special actions are {list(BrowserActionId)}"
                        )
                    ),
                )

    @staticmethod
    def forward_parameter_action(action: ExecutableAction) -> InteractionAction:
        if action.locator is None:
            raise NodeResolutionAttributeError(None, "post_attributes")  # type: ignore
        if len(action.params) != 1:
            raise MoreThanOneParameterActionError(action.id, len(action.params))
        value: str = action.params[0].values[0]
        node_role = action.locator.role if isinstance(action.locator.role, str) else action.locator.role.value
        match (action.role, node_role, action.locator.is_editable):
            case (_, _, True) | ("input", "textbox", _):
                return FillAction(selector=action.locator.selector, value=value)
            case ("input", "checkbox", _):
                return CheckAction(selector=action.locator.selector, value=bool(value))
            case ("input", "combobox", _):
                return SelectAction(selector=action.locator.selector, value=value)
            case ("input", _, _):
                return FillAction(selector=action.locator.selector, value=value)
            case _:
                raise InvalidActionError(action.id, f"unknown action type: {action.id[0]}")

    @staticmethod
    def forward(action: ExecutableAction) -> BaseAction:
        if action.locator is None:
            raise NodeResolutionAttributeError(None, "post_attributes")

        match action.role:
            case "button":
                return ClickAction(selector=action.locator.selector)
            case "special":
                return NotteActionProxy.forward_special(action)
            case "input":
                return NotteActionProxy.forward_parameter_action(action)
            case _:
                raise InvalidActionError(action.id, f"unknown action type: {action.id[0]}")
