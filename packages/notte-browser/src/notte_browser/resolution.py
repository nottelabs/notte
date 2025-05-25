from loguru import logger
from notte_core.actions.base import ExecutableAction
from notte_core.browser.dom_tree import InteractionDomNode, NodeSelectors
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.controller.actions import (
    BaseAction,
    BrowserAction,
    InteractionAction,
)
from notte_core.controller.proxy import NotteActionProxy
from notte_core.errors.actions import InvalidActionError

from notte_browser.dom.locate import selectors_through_shadow_dom
from notte_browser.errors import FailedNodeResolutionError


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
            raise InvalidActionError("unknown", "snapshot is required to resolve selectors for interaction actions")

        if isinstance(action, ExecutableAction):
            node = snapshot.dom_node.find(action.id)
            if node is None:
                raise InvalidActionError(action.id, "node cannot be None to be able to execute an interaction action")
            action = NotteActionProxy.forward(action, node=node)

        if not isinstance(action, InteractionAction):
            raise InvalidActionError("unknown", f"action is not an interaction action: {action.type}")
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
