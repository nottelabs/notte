from collections.abc import Sequence
from dataclasses import dataclass

from notte.actions.base import Action
from notte.browser.dom_tree import DomNode, InteractionDomNode
from notte.browser.snapshot import BrowserSnapshot


@dataclass
class ProcessedBrowserSnapshot:
    node: DomNode
    snapshot: BrowserSnapshot

    def interaction_nodes(self) -> Sequence[InteractionDomNode]:
        return self.node.interaction_nodes()

    def subgraph_without(
        self, actions: Sequence[Action], roles: set[str] | None = None
    ) -> "ProcessedBrowserSnapshot | None":
        if len(actions) == 0 and roles is not None:
            subgraph = self.node.subtree_without(roles)
            return ProcessedBrowserSnapshot(
                snapshot=self.snapshot,
                node=subgraph,
            )
        id_existing_actions = set([action.id for action in actions])
        failed_actions = {node.id for node in self.interaction_nodes() if node.id not in id_existing_actions}

        def only_failed_actions(node: DomNode) -> bool:
            return len(set(node.subtree_ids).intersection(failed_actions)) > 0

        filtered_graph = self.node.subtree_filter(only_failed_actions)
        if filtered_graph is None:
            return None

        return ProcessedBrowserSnapshot(
            snapshot=self.snapshot,
            node=filtered_graph,
        )
