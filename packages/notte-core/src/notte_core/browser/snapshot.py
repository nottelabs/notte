import datetime as dt
from base64 import b64encode
from collections.abc import Sequence
from dataclasses import dataclass, field

from loguru import logger
from PIL import Image
from pydantic import BaseModel

from notte_core.actions import InteractionAction
from notte_core.browser.dom_tree import A11yTree, DomNode, InteractionDomNode
from notte_core.errors.base import AccessibilityTreeMissingError
from notte_core.utils.url import clean_url


class TabsData(BaseModel):
    tab_id: int
    title: str
    url: str


class ViewportData(BaseModel):
    scroll_x: int
    scroll_y: int
    viewport_width: int
    viewport_height: int
    total_width: int
    total_height: int

    @property
    def pixels_above(self) -> int:
        return self.scroll_y

    @property
    def pixels_below(self) -> int:
        return self.total_height - self.scroll_y - self.viewport_height


class SnapshotMetadata(BaseModel):
    title: str
    url: str
    viewport: ViewportData
    tabs: list[TabsData]
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)


@dataclass
class BrowserDialog:
    """Information about a browser dialog (alert, confirm, prompt)"""

    type: str
    message: str
    nodes: list[DomNode]


class BrowserSnapshot(BaseModel):
    metadata: SnapshotMetadata
    html_content: str
    a11y_tree: A11yTree | None
    dom_node: DomNode
    screenshot: bytes
    browser_dialog: BrowserDialog | None = None  # Add dialog info to snapshot

    model_config = {  # pyright: ignore [reportUnannotatedClassAttribute]
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }

    def display_screenshot(self) -> "Image.Image | None":
        from notte_core.utils.image import image_from_bytes

        if self.screenshot is None:  # pyright: ignore [reportUnnecessaryComparison]
            return None
        return image_from_bytes(self.screenshot)

    @property
    def clean_url(self) -> str:
        return clean_url(self.metadata.url)

    def compare_with(self, other: "BrowserSnapshot") -> bool:
        if self.a11y_tree is None or other.a11y_tree is None:
            raise AccessibilityTreeMissingError()

        inodes = {node.id for node in self.dom_node.interaction_nodes()}
        new_inodes = {node.id for node in other.dom_node.interaction_nodes()}
        identical = inodes == new_inodes
        if not identical:
            logger.trace(f"Interactive nodes changed: {new_inodes.difference(inodes)}")
        return identical

    def interaction_nodes(self) -> Sequence[InteractionDomNode]:
        return self.dom_node.interaction_nodes()

    def with_dom_node(self, dom_node: DomNode) -> "BrowserSnapshot":
        return BrowserSnapshot(
            metadata=self.metadata,
            html_content=self.html_content,
            a11y_tree=self.a11y_tree,
            dom_node=dom_node,
            screenshot=self.screenshot,
            browser_dialog=self.browser_dialog,
        )

    def subgraph_without(
        self, actions: Sequence[InteractionAction], roles: set[str] | None = None
    ) -> "BrowserSnapshot | None":
        if len(actions) == 0 and roles is not None:
            subgraph = self.dom_node.subtree_without(roles)
            return self.with_dom_node(subgraph)
        id_existing_actions = set([action.id for action in actions])
        failed_actions = {node.id for node in self.interaction_nodes() if node.id not in id_existing_actions}

        def only_failed_actions(node: DomNode) -> bool:
            return len(set(node.subtree_ids).intersection(failed_actions)) > 0

        filtered_graph = self.dom_node.subtree_filter(only_failed_actions)
        if filtered_graph is None:
            return None

        return self.with_dom_node(filtered_graph)
