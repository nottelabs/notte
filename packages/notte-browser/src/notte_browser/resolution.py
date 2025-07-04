from loguru import logger
from notte_core.actions import (
    BaseAction,
    BrowserAction,
    InteractionAction,
)
from notte_core.browser.dom_tree import InteractionDomNode, NodeSelectors
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.errors.actions import InvalidActionError
from notte_core.profiling import profiler

from notte_browser.dom.locate import selectors_through_shadow_dom
from notte_browser.errors import FailedNodeResolutionError, NoSnapshotObservedError


class NodeResolutionPipe:
    @profiler.profiled()
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

        if action.type == "step":
            raise ValueError("Step action is not supported anymore. Use the appropriate action instead.")

        if not isinstance(action, InteractionAction):
            raise InvalidActionError("unknown", f"action is not an interaction action: {action.type}")
        # resolve selector
        selector_map: dict[str, InteractionDomNode] = {inode.id: inode for inode in snapshot.interaction_nodes()}
        is_id_resolved = action.id in selector_map
        if action.selector is not None:
            # skip resolution if selector is provided
            if not is_id_resolved:
                logger.warning(
                    f"🚨 Action '{action.type}' has an external selector but its id={action.id} is not found in page context. This could lead to unexpected behavior. Proceeding with resolution."
                )
            return action

        if not is_id_resolved:
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
