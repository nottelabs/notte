from typing import final

from notte.browser.context import Context
from notte.browser.node_type import A11yNode, NodeAttributesPre, NodeRole, NotteNode
from notte.browser.snapshot import BrowserSnapshot
from notte.pipe.preprocessing.a11y.tree import ProcessedA11yTree


@final
class ActionA11yPipe:

    @staticmethod
    def forward(snapshot: BrowserSnapshot) -> Context:
        processed_tree = ProcessedA11yTree.from_a11y_tree(snapshot.a11y_tree)

        def to_notte_node(node: A11yNode, path: str) -> NotteNode:
            node_path = ":".join([path, node["role"], node["name"]])
            children = [
                to_notte_node(child, node_path) for child in node.get("children", [])
            ]
            return NotteNode(
                id=node.get("id"),
                role=NodeRole.from_value(node["role"]),
                text=node["name"],
                children=children,
                attributes_pre=NodeAttributesPre(
                    modal=node.get("modal"),
                    required=node.get("required"),
                    description=node.get("description"),
                    visible=node.get("visible"),
                    selected=node.get("selected"),
                    checked=node.get("checked"),
                    enabled=node.get("enabled"),
                    path=node_path,
                ),
            )

        return Context(
            snapshot=snapshot,
            node=to_notte_node(processed_tree.processed_tree, path=snapshot.url),
        )
