from dataclasses import dataclass

from notte.actions.base import Action
from notte.browser.node_type import InteractionNode, NotteNode
from notte.browser.snapshot import BrowserSnapshot


@dataclass
class Context:
    node: NotteNode
    snapshot: BrowserSnapshot

    def interaction_nodes(self) -> list[InteractionNode]:
        return self.node.interaction_nodes()

    def markdown_description(self) -> str:
        return self.format(self.node, indent_level=0)

    def format(
        self,
        node: NotteNode,
        indent_level: int = 0,  # indentation level for the current node.
        cumulative_chars: int = 0,  # carries on num_chars from parent nodes.
        parent_path: list[int] | None = None,  # computes the path to a given node.
    ) -> str:
        indent = "  " * indent_level
        parent_path = parent_path or []

        # Start with role and optional text
        result = f"{indent}{node.get_role_str()}"
        if node.text is not None and node.text != "":
            result += f' "{node.text}"'

        # Add attributes
        attrs = []
        if node.id is not None:
            attrs.append(node.id)
        if node.attributes_pre.modal is not None:
            attrs.append("modal")
        if node.attributes_pre.required is not None:
            attrs.append("required")
        if node.attributes_pre.description is not None:
            attrs.append(f'desc="{node.attributes_pre.description}"')

        if attrs:
            result += " " + " ".join(attrs)

        # estimate the upper bound of the number of chars for current node.
        cumulative_ub = cumulative_chars + len(result) + 5 * (indent_level + 1)

        # Recursively format children
        if len(node.children) > 0:
            result += " {\n"
            for i, child in enumerate(node.children):
                result += self.format(child, indent_level + 1, cumulative_ub, parent_path + [i])
            result += indent + "}\n"
        else:
            result += "\n"

        node._subtree_chars = len(result)
        node._chars = len(result) + cumulative_chars
        node._path = parent_path

        return result

    def subgraph_without(self, actions: list[Action]) -> "Context":

        id_existing_actions = set([action.id for action in actions])
        failed_actions = {
            node.id for node in self.interaction_nodes() if node.id is not None and node.id not in id_existing_actions
        }

        def only_failed_actions(node: NotteNode) -> bool:
            return len(set(node.subtree_ids).intersection(failed_actions)) > 0

        filtered_graph = self.node.subtree_filter(only_failed_actions)
        if filtered_graph is None:
            raise ValueError("No nodes left after filtering of exesting actions")

        return Context(
            snapshot=self.snapshot,
            node=filtered_graph,
        )
