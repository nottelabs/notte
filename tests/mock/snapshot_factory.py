from notte_core.dom_tree import ComputedDomAttributes, DomAttributes, DomNode
from notte_core.node_type import NodeType
from notte_core.observation import Observation
from notte_core.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData


def make_snapshot(url: str) -> BrowserSnapshot:
    return BrowserSnapshot(
        metadata=SnapshotMetadata(
            title="mock",
            url=url,
            viewport=ViewportData(
                scroll_x=0,
                scroll_y=0,
                viewport_width=1000,
                viewport_height=1000,
                total_width=1000,
                total_height=1000,
            ),
            tabs=[],
        ),
        html_content="<html></html>",
        dom_node=DomNode(
            id="root",
            type=NodeType.OTHER,
            role="WebArea",
            text="",
            children=[],
            attributes=DomAttributes.safe_init(tag_name="div"),
            computed_attributes=ComputedDomAttributes(),
        ),
        screenshot=Observation.empty().screenshot.raw,
    )
