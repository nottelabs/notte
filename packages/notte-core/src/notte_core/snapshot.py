import datetime as dt
from base64 import b64encode
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from notte_core.dom_tree import DomNode
from notte_core.element_state import ElementState, page_fingerprint
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

    def element_states(self) -> dict[str, ElementState]:
        """The live state of the interaction nodes that have one, by action id (e.g. `I1`)."""
        nodes = self.dom_node.interaction_nodes_by_id
        return {node_id: node.state for node_id, node in nodes.items() if node.state is not None}

    def fingerprint(self, states: Mapping[str, ElementState] | None = None) -> str:
        """A cheap marker of the page state: URL, and the id, label and live state of every
        interaction node. It changes when the page offers other actions or a field value changes,
        so a decision taken on this snapshot can be checked against a newer one before acting.
        `states` replaces the nodes' own state (e.g. with secrets masked)."""
        nodes = self.dom_node.interaction_nodes_by_id
        return page_fingerprint(
            self.metadata.url,
            # `inner_text()` is the action label (what interaction nodes used to carry as `text`).
            (
                (node_id, node.inner_text(), node.state if states is None else states.get(node_id))
                for node_id, node in nodes.items()
            ),
        )
