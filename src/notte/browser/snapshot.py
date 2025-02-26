import datetime as dt
from base64 import b64encode
from dataclasses import field

from loguru import logger
from pydantic import BaseModel

from notte.browser.dom_tree import A11yTree, DomNode
from notte.pipe.preprocessing.a11y.traversal import set_of_interactive_nodes
from notte.utils.url import clean_url


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


class BrowserSnapshot(BaseModel):
    metadata: SnapshotMetadata
    html_content: str
    a11y_tree: A11yTree
    dom_node: DomNode
    screenshot: bytes | None

    model_config = {  # type: ignore[reportUnknownMemberType]
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }

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
