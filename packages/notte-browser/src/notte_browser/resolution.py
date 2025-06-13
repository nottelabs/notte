from loguru import logger
from notte_core.actions import (
    BaseAction,
    BrowserAction,
    CheckAction,
    ClickAction,
    FillAction,
    InteractionAction,
    SelectDropdownOptionAction,
    StepAction,
)
from notte_core.browser.dom_tree import DomNode, InteractionDomNode, NodeSelectors
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.credentials.types import get_str_value
from notte_core.errors.actions import InputActionShouldHaveOneParameterError, InvalidActionError

from notte_browser.dom.locate import selectors_through_shadow_dom
from notte_browser.errors import FailedNodeResolutionError, NoSnapshotObservedError


class NodeResolutionPipe:
    @staticmethod
    def forward(
        action: BaseAction,
        snapshot: BrowserSnapshot | None,
        verbose: bool = False,
    ) -> InteractionAction | BrowserAction:
        if isinstance(action, BrowserAction):
            # nothing to do here
            return action

        if snapshot is None:
            raise NoSnapshotObservedError()

        if isinstance(action, StepAction):
            node = snapshot.dom_node.find(action.id)
            if node is None:
                raise InvalidActionError(action.id, "node cannot be None to be able to execute an interaction action")
            action = NotteActionProxy.forward(action, node=node)

        if not isinstance(action, InteractionAction):
            raise InvalidActionError("unknown", f"action is not an interaction action: {action.type}")

        if not action.bypass_action_resolution:
            # resolve selector
            selector_map: dict[str, InteractionDomNode] = {inode.id: inode for inode in snapshot.interaction_nodes()}
            if action.id not in selector_map:
                raise InvalidActionError(action_id=action.id, reason=f"action '{action.id}' not found in page context.")
            node = selector_map[action.id]
            action.selector = NodeResolutionPipe.resolve_selectors(node, verbose)
            action.text_label = node.text

        return action

    @staticmethod
    def resolve_selectors(node: InteractionDomNode, verbose: bool = False) -> NodeSelectors:
        if node.computed_attributes.selectors is None:
            raise FailedNodeResolutionError(node.id)
        selectors = node.computed_attributes.selectors
        if selectors.in_shadow_root:
            if verbose:
                logger.info(f"🔍 Resolving shadow root selectors for {node.id} ({node.text})")
            selectors = selectors_through_shadow_dom(node)
        return selectors


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
    def forward_parameter_action(action: StepAction, node: DomNode) -> InteractionAction:
        if action.value is None:
            raise InputActionShouldHaveOneParameterError(action.id)
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
                    value=NotteActionProxy._parse_boolean(value),
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
    def forward(action: StepAction, node: DomNode) -> InteractionAction:
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
