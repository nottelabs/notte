import datetime as dt
from dataclasses import dataclass, field

from loguru import logger

from notte.browser.dom_tree import A11yTree, DomNode
from notte.pipe.preprocessing.a11y.traversal import set_of_interactive_nodes
from notte.utils.url import clean_url


@dataclass
class TabsData:
    tab_id: int
    title: str
    url: str


@dataclass
class ViewportData:
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


@dataclass
class SnapshotMetadata:
    title: str
    url: str
    viewport: ViewportData
    tabs: list[TabsData]
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)


@dataclass
class BrowserSnapshot:
    metadata: SnapshotMetadata
    html_content: str
    a11y_tree: A11yTree
    dom_node: DomNode
    screenshot: bytes | None

    @property
    def clean_url(self) -> str:
        return clean_url(self.metadata.url)

    def compare_with(self, other: "BrowserSnapshot") -> bool:
        inodes = set_of_interactive_nodes(self.a11y_tree.simple)
        new_inodes = set_of_interactive_nodes(other.a11y_tree.simple)
        identical = inodes == new_inodes
        if not identical:
            logger.warning(f"Interactive nodes changed: {new_inodes.difference(inodes)}")
        return identical
