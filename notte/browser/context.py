from dataclasses import dataclass

from loguru import logger

from notte.actions.base import Action
from notte.browser.node_type import InteractionNode, NodeCategory, NotteNode
from notte.browser.snapshot import BrowserSnapshot


@dataclass
class Context:
    node: NotteNode
    snapshot: BrowserSnapshot

    def interaction_nodes(self) -> list[InteractionNode]:
        return self.node.interaction_nodes()

    def markdown_description(self, include_ids: bool = True, include_images: bool = False) -> str:
        return self.format(self.node, indent_level=0, include_ids=include_ids, include_images=include_images)

    def format(
        self,
        node: NotteNode,
        include_ids: bool = True,
        include_images: bool = False,
        indent_level: int = 0,  # indentation level for the current node.
        cumulative_chars: int = 0,  # carries on num_chars from parent nodes.
        parent_path: list[int] | None = None,  # computes the path to a given node.
    ) -> str:
        indent = "  " * indent_level
        parent_path = parent_path or []

        # Exclude images if requested
        if not include_images:
            node = node.subtree_without(NodeCategory.IMAGE.roles(), deepcopy=False)

        # Start with role and optional text
        result = f"{indent}{node.get_role_str()}"
        if node.text is not None and node.text != "":
            result += f' "{node.text}"'

        # Add attributes
        attrs: list[str] = []
        if node.id is not None and (
            include_ids or (include_images and node.get_role_str() in NodeCategory.IMAGE.roles())
        ):
            attrs.append(node.id)

        # iterate pre-over attributes
        attrs.extend(node.attributes_pre.relevant_attrs())

        if attrs:
            # TODO: prompt engineering to select the most readable format
            # for the LLM to understand this information
            result += " " + " ".join(attrs)

        # estimate the upper bound of the number of chars for current node.
        cumulative_ub = cumulative_chars + len(result) + 5 * (indent_level + 1)

        # Recursively format children
        if len(node.children) > 0:
            result += " {\n"
            for i, child in enumerate(node.children):
                result += self.format(
                    child, include_ids, include_images, indent_level + 1, cumulative_ub, parent_path + [i]
                )
            result += indent + "}\n"
        else:
            result += "\n"

        node._subtree_chars = len(result)
        node._chars = len(result) + cumulative_chars
        node._path = parent_path

        return result

    def subgraph_without(self, actions: list[Action]) -> "Context | None":

        id_existing_actions = set([action.id for action in actions])
        failed_actions = {node.id for node in self.interaction_nodes() if node.id not in id_existing_actions}

        def only_failed_actions(node: NotteNode) -> bool:
            return len(set(node.subtree_ids).intersection(failed_actions)) > 0

        filtered_graph = self.node.subtree_filter(only_failed_actions)
        if filtered_graph is None:
            logger.error(f"No nodes left in context after filtering of exesting actions for url {self.snapshot.url}")
            return None

        return Context(
            snapshot=self.snapshot,
            node=filtered_graph,
        )
