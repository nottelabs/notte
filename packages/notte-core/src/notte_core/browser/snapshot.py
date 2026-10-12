import datetime as dt
from base64 import b64encode
from collections.abc import Sequence

from pydantic import BaseModel, Field

from notte_core.browser.dom_tree import A11yTree, DomNode, InteractionDomNode
from notte_core.common.logging import logger
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


class SnapshotMetadata(BaseModel):
    title: str
    url: str
    viewport: ViewportData
    tabs: list[TabsData]
    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc), description="Timestamp of the snapshot"
    )


class BrowserSnapshot(BaseModel):
    metadata: SnapshotMetadata
    html_content: str
    a11y_tree: A11yTree | None
    dom_node: DomNode
    screenshot: bytes = Field(repr=False)

    model_config = {  # type: ignore[reportUnknownMemberType]
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }

    @property
    def clean_url(self) -> str:
        return clean_url(self.metadata.url)

    def compare_with(self, other: "BrowserSnapshot") -> bool:
        inodes = {node.id for node in self.dom_node.interaction_nodes()}
        new_inodes = {node.id for node in other.dom_node.interaction_nodes()}
        identical = inodes == new_inodes
        if not identical:
            logger.trace(f"Interactive nodes changed: {new_inodes.difference(inodes)}")
        return identical

    def interaction_nodes(self) -> Sequence[InteractionDomNode]:
        return self.dom_node.interaction_nodes()
