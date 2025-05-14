from pydantic import BaseModel, Field
from typing_extensions import override

from notte_core.actions.base import (
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
from notte_core.browser.dom_tree import DomNode, NodeSelectors
from notte_core.credentials.types import ValueWithPlaceholder, get_str_value
from notte_core.errors.actions import InvalidActionError, MoreThanOneParameterActionError


class ActionParameter(BaseModel):
    name: str
    type: str
    default: str | None = None
    values: list[str] = Field(default_factory=list)

    def description(self) -> str:
        base = f"{self.name}: {self.type}"
        if len(self.values) > 0:
            base += f" = [{', '.join(self.values)}]"
        return base


class ActionParameterValue(BaseModel):
    name: str
    value: str | ValueWithPlaceholder


class PerceivedAction(InteractionAction):
    """
    An output of the perception layer (i.e tagged action)
    """

    id: str
    description: str
    category: str  # pyright: ignore[reportGeneralTypeIssues]
    params: list[ActionParameter] = Field(default_factory=list)

    def markdown(self) -> str:
        return self.description

    @override
    def execution_message(self) -> str:
        # TODO: think about a better message here
        return f"Sucessfully executed: '{self.description}'"


class ExecPerceivedAction(BaseAction):
    """
    An action that can be executed by the proxy.
    """

    id: str
    # description is not needed for the proxy
    category: str = "Executable action"
    description: str = "Executable action"
    value: str | ValueWithPlaceholder | None = None
    press_enter: bool | None = None
    selector: NodeSelectors | None = None

    @override
    def execution_message(self) -> str:
        # TODO: think about a better message here
        return f"Sucessfully executed: '{self.description}'"

    def to_controller_action(self, node: DomNode) -> InteractionAction | BrowserAction:
        return NotteActionProxy.forward(self, node)


# ############################################################
# ############################################################
# ############################################################


class NotteActionProxy:
    @staticmethod
    def forward_special(action: ExecPerceivedAction) -> BrowserAction:
        match action.id:
            case BrowserActionId.GOTO.value:
                assert action.value is not None
                return GotoAction(url=get_str_value(action.value))
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
                assert action.value is not None
                return CompletionAction(success=bool(action.value), answer=get_str_value(action.value))
            case BrowserActionId.PRESS_KEY.value:
                assert action.value is not None
                return PressKeyAction(key=get_str_value(action.value))
            case BrowserActionId.SCROLL_UP.value:
                assert action.value is not None
                return ScrollUpAction(amount=int(get_str_value(action.value)))
            case BrowserActionId.SCROLL_DOWN.value:
                assert action.value is not None
                return ScrollDownAction(amount=int(get_str_value(action.value)))
            case BrowserActionId.WAIT.value:
                assert action.value is not None
                return WaitAction(time_ms=int(get_str_value(action.value)))
            case BrowserActionId.GOTO_NEW_TAB.value:
                assert action.value is not None
                return GotoNewTabAction(url=get_str_value(action.value))
            case BrowserActionId.SWITCH_TAB.value:
                assert action.value is not None
                return SwitchTabAction(tab_index=int(get_str_value(action.value)))
            case _:
                raise InvalidActionError(
                    action_id=action.id,
                    reason=(
                        f"try executing a special action but '{action.id}' is not a special action. "
                        f"Special actions are {list(BrowserActionId)}"
                    ),
                )

    @staticmethod
    def forward_parameter_action(action: ExecPerceivedAction, node: DomNode) -> InteractionAction:
        if action.value is None:
            raise MoreThanOneParameterActionError(action.id, 0)
        value: str = get_str_value(action.value)
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
    def forward(action: ExecPerceivedAction, node: DomNode) -> InteractionAction | BrowserAction:
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
            case "special":
                return NotteActionProxy.forward_special(action)
            case _:
                raise InvalidActionError(action.id, f"unknown action role: {action.role} with id: {action.id}")
