import datetime as dt
from base64 import b64encode
from collections.abc import Sequence

from pydantic import BaseModel, Field

from notte_core.browser.dom_tree import DomNode
from notte_core.url import clean_url


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
    dom_node: DomNode
    # None when the snapshot was taken with `screenshot=False` (e.g. scrapes)
    screenshot: bytes | None = Field(default=None, repr=False)

    model_config = {  # type: ignore[reportUnknownMemberType]
        "json_encoders": {
            bytes: lambda v: b64encode(v).decode("utf-8") if v else None,
        }
    }

    @property
    def clean_url(self) -> str:
        return clean_url(self.metadata.url)

    def interaction_nodes(self) -> Sequence[DomNode]:
        return self.dom_node.interaction_nodes()
