from loguru import logger

from notte.browser.dom_tree import InteractionDomNode, NodeSelectors
from notte.browser.node_type import NodeRole
from notte.browser.snapshot import BrowserSnapshot
from notte.controller.actions import (
    BrowserAction,
    ClickAction,
    InteractionAction,
    SelectDropdownOptionAction,
)
from notte.errors.actions import InvalidActionError
from notte.errors.resolution import FailedSimpleNodeResolutionError
from notte.pipe.preprocessing.dom.locate import selectors_through_shadow_dom


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
        if isinstance(action, SelectDropdownOptionAction):
            select_action = SimpleActionResolutionPipe.resolve_dropdown_locators(action, snapshot, verbose)
            if select_action is not None:
                return select_action
            # hack: fallback to click action if no selector is found
            if verbose:
                logger.warning(
                    f"🚸 No selector found for select dropdown action with id={action.id}, falling back to click action"
                )
            fallback_action = ClickAction(id=action.id)
            return SimpleActionResolutionPipe.forward(fallback_action, snapshot, verbose)

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
            raise FailedSimpleNodeResolutionError(node.id)
        selectors = node.computed_attributes.selectors
        if selectors.in_shadow_root:
            if verbose:
                logger.info(f"🔍 Resolving shadow root selectors for {node.id} ({node.text})")
            selectors = selectors_through_shadow_dom(node)
        return selectors

    @staticmethod
    def resolve_dropdown_locators(
        action: SelectDropdownOptionAction,
        snapshot: BrowserSnapshot,
        verbose: bool = False,
    ) -> SelectDropdownOptionAction | None:
        """
        Resolve the selector locators for a dropdown option.

        We need to find the selector node and the option node.
        This function simply iterates over the interaction nodes to find the option node.
        The selector node is the first node with a role in [COMBOBOX, LISTBOX, LIST]
        that appears before the option node.
        """
        inodes = snapshot.dom_node.interaction_nodes()
        snode = None
        for node in inodes:
            if node.get_role_str() in [NodeRole.COMBOBOX.value, NodeRole.LISTBOX.value, NodeRole.LIST.value]:
                snode = node
            if (action.option_id is not None and node.id == action.option_id) or (
                action.value is not None and node.text == action.value and node.get_role_str() == NodeRole.OPTION.value
            ):
                if snode is None:
                    raise ValueError(f"No select html element found for {action.option_id} or {action.value}")

                if node.computed_attributes.selectors is None or snode.computed_attributes.selectors is None:
                    raise FailedSimpleNodeResolutionError(action.id)
                selectors = snode.computed_attributes.selectors
                option_selectors = node.computed_attributes.selectors
                if verbose:
                    logger.info(
                        (
                            f"Resolved locators for select dropdown {snode.id} ({snode.text})"
                            f" and option {node.id} ({node.text})"
                        )
                    )
                action.option_selector = option_selectors
                action.selector = selectors
                return action

        return None
