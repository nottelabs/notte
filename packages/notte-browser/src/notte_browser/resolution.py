from loguru import logger
from notte_core.actions.base import (
    BaseAction,
    BrowserAction,
    InteractionAction,
)
from notte_core.actions.percieved import ExecPerceivedAction
from notte_core.browser.dom_tree import InteractionDomNode, NodeSelectors
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.errors.actions import InvalidActionError

from notte_browser.dom.locate import selectors_through_shadow_dom
from notte_browser.errors import FailedNodeResolutionError


class SimpleActionResolutionPipe:
    @staticmethod
    def forward(
        action: InteractionAction | BrowserAction,
        snapshot: BrowserSnapshot | None = None,
        verbose: bool = False,
    ) -> InteractionAction | BrowserAction:
        if not isinstance(action, InteractionAction) or snapshot is None:
            # no need to resolve
            return action

        selector_map: dict[str, InteractionDomNode] = {inode.id: inode for inode in snapshot.interaction_nodes()}
        if action.id not in selector_map:
            raise InvalidActionError(action_id=action.id, reason=f"action '{action.id}' not found in page context.")
        node = selector_map[action.id]
        action.selector = SimpleActionResolutionPipe.resolve_selectors(node, verbose)
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


class NodeResolutionPipe:
    @staticmethod
    async def forward(
        action: BaseAction,
        snapshot: BrowserSnapshot | None,
        verbose: bool = False,
    ) -> InteractionAction | BrowserAction:
        if isinstance(action, ExecPerceivedAction):
            if snapshot is not None:
                node = snapshot.dom_node.find(action.id)
                if node is None:
                    raise FailedNodeResolutionError(action.id)
                action = action.to_controller_action(node)
                if verbose:
                    logger.info(f"Resolving to action {action.dump_str()}")

        return SimpleActionResolutionPipe.forward(action, snapshot=snapshot, verbose=verbose)  # pyright: ignore[reportArgumentType]
