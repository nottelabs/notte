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

    def markdown_description(self, include_ids: bool = True) -> str:
        return Context.format(self.node, indent_level=0, include_ids=include_ids)

    @staticmethod
    def format(node: NotteNode, indent_level: int = 0, include_ids: bool = True) -> str:
        indent = "  " * indent_level

        # Start with role and optional text
        result = f"{indent}{node.get_role_str()}"
        if node.text is not None and node.text != "":
            result += f' "{node.text}"'

        # Add attributes
        attrs: list[str] = []
        if node.id is not None and include_ids:
            attrs.append(node.id)

        # iterate pre-over attributes
        attrs.extend(node.attributes_pre.relevant_attrs())

        if attrs:
            # TODO: prompt engineering to select the most readable format
            # for the LLM to understand this information
            result += " " + " ".join(attrs)

        # Recursively format children
        if len(node.children) > 0:
            result += " {\n"
            for child in node.children:
                result += Context.format(child, indent_level + 1, include_ids=include_ids)
            result += indent + "}\n"
        else:
            result += "\n"

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
