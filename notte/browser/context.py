from dataclasses import dataclass
from typing import Any

from PIL import Image

from notte.actions.base import Action
from notte.actions.space import ActionSpace
from notte.browser.node_type import NotteNode
from notte.browser.snapshot import BrowserSnapshot
from notte.utils import image


@dataclass
class Observation:
    url: str
    screenshot: bytes | None = None
    space: ActionSpace | None = None

    def display_screenshot(self) -> Image.Image | None:
        if self.screenshot is None:
            return None
        return image.image_from_bytes(self.screenshot)

    @staticmethod
    def from_json(json: dict[str, Any]) -> "Observation":
        return Observation(
            url=json["url"],
            screenshot=json["screenshot"],
            space=ActionSpace.from_json(json["space"]),
        )


@dataclass
class Context:
    node: NotteNode
    snapshot: BrowserSnapshot

    def interaction_nodes(self) -> list[NotteNode]:
        return self.node.flatten(only_interaction=True)

    def markdown_description(self) -> str:
        return self.format(self.node, indent_level=0)

    def format(self, node: NotteNode, indent_level: int = 0) -> str:
        indent = "  " * indent_level

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

        # Recursively format children
        if len(node.children) > 0:
            result += " {\n"
            for child in node.children:
                result += self.format(child, indent_level + 1)
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
