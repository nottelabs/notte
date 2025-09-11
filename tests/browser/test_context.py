import pytest
from notte_core.actions import ClickAction
from notte_core.browser.dom_tree import A11yNode, A11yTree, ComputedDomAttributes, DomNode
from notte_core.browser.node_type import NodeRole, NodeType
from notte_core.browser.observation import Observation
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData


@pytest.fixture
def nested_graph() -> DomNode:
    return DomNode(
        id=None,
        role=NodeRole.GROUP,
        text="root",
        type=NodeType.OTHER,
        computed_attributes=ComputedDomAttributes(),
        attributes=None,
        children=[
            DomNode(
                id="A1",
                role=NodeRole.BUTTON,
                text="A1",
                type=NodeType.INTERACTION,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id="A2",
                role=NodeRole.BUTTON,
                text="A2",
                type=NodeType.INTERACTION,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id="A3",
                role=NodeRole.BUTTON,
                text="A3",
                type=NodeType.INTERACTION,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id=None,
                role=NodeRole.TEXT,
                text="text",
                type=NodeType.TEXT,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id=None,
                role=NodeRole.GROUP,
                text="yo",
                type=NodeType.OTHER,
                computed_attributes=ComputedDomAttributes(),
                attributes=None,
                children=[
                    DomNode(
                        id="B1",
                        role=NodeRole.BUTTON,
                        text="B1",
                        type=NodeType.INTERACTION,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                    DomNode(
                        id="B2",
                        role=NodeRole.BUTTON,
                        text="B2",
                        type=NodeType.INTERACTION,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                    DomNode(
                        id=None,
                        role=NodeRole.TEXT,
                        text="text",
                        type=NodeType.TEXT,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                ],
            ),
            DomNode(
                id="A4",
                role=NodeRole.BUTTON,
                text="A4",
                type=NodeType.INTERACTION,
                children=[],
                attributes=None,
                computed_attributes=ComputedDomAttributes(),
            ),
            DomNode(
                id=None,
                role=NodeRole.GROUP,
                text="B2",
                type=NodeType.OTHER,
                computed_attributes=ComputedDomAttributes(),
                attributes=None,
                children=[
                    DomNode(
                        id="B3",
                        role=NodeRole.BUTTON,
                        text="B3",
                        type=NodeType.INTERACTION,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                    DomNode(
                        id="B4",
                        role=NodeRole.BUTTON,
                        text="B4",
                        type=NodeType.INTERACTION,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                    DomNode(
                        id=None,
                        role=NodeRole.TEXT,
                        text="text",
                        type=NodeType.TEXT,
                        children=[],
                        attributes=None,
                        computed_attributes=ComputedDomAttributes(),
                    ),
                    DomNode(
                        id=None,
                        role=NodeRole.GROUP,
                        text="C",
                        type=NodeType.OTHER,
                        computed_attributes=ComputedDomAttributes(),
                        attributes=None,
                        children=[
                            DomNode(
                                id="C1",
                                role=NodeRole.BUTTON,
                                text="C1",
                                type=NodeType.INTERACTION,
                                children=[],
                                attributes=None,
                                computed_attributes=ComputedDomAttributes(),
                            ),
                            DomNode(
                                id="C2",
                                role=NodeRole.BUTTON,
                                text="C2",
                                type=NodeType.INTERACTION,
                                children=[],
                                attributes=None,
                                computed_attributes=ComputedDomAttributes(),
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def browser_snapshot() -> BrowserSnapshot:
    empty_a11y_tree = A11yNode(
        role="root",
        name="root",
        children=[],
    )
    return BrowserSnapshot(
        metadata=SnapshotMetadata(
            url="https://example.com",
            title="example",
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
        html_content="my html content",
        a11y_tree=A11yTree(empty_a11y_tree, empty_a11y_tree),
        screenshot=Observation.empty().screenshot.raw,
        dom_node=DomNode(
            id="B2",
            role="button",
            text="user-text",
            type=NodeType.INTERACTION,
            children=[],
            attributes=None,
            computed_attributes=ComputedDomAttributes(),
        ),
    )


def test_subgraph_without_existing_actions(
    nested_graph: DomNode,
    browser_snapshot: BrowserSnapshot,
) -> None:
    context = browser_snapshot.with_dom_node(nested_graph)
    assert len(context.interaction_nodes()) == 10, [inode.id for inode in context.interaction_nodes()]
    # test with A1
    subgraph = context.subgraph_without([ClickAction(id="A1", description="A1", category="A1")])
    assert subgraph is not None
    assert subgraph.dom_node.find("A1") is None
    assert len(subgraph.interaction_nodes()) == 9, [inode.id for inode in subgraph.interaction_nodes()]
    # test with A1, A2, A3
    subgraph = context.subgraph_without(
        [
            ClickAction(id="A1", description="A1", category="A1"),
            ClickAction(id="A2", description="A2", category="A2"),
            ClickAction(id="A3", description="A3", category="A3"),
        ]
    )
    assert subgraph is not None
    assert subgraph.dom_node.find("A1") is None
    assert subgraph.dom_node.find("A2") is None
    assert subgraph.dom_node.find("A3") is None
    assert len(subgraph.interaction_nodes()) == 7
    # test with B1, B2, C2
    subgraph = context.subgraph_without(
        [
            ClickAction(id="A1", description="A1", category="A1"),
            ClickAction(id="A2", description="A2", category="A2"),
            ClickAction(id="A3", description="A3", category="A3"),
            ClickAction(id="B1", description="B1", category="B1"),
            ClickAction(id="B2", description="B2", category="B2"),
            ClickAction(id="C2", description="C2", category="C2"),
        ]
    )
    assert subgraph is not None
    assert subgraph.dom_node.find("B1") is None
    assert subgraph.dom_node.find("B2") is None
    assert subgraph.dom_node.find("C2") is None
    assert len(subgraph.interaction_nodes()) == 4
    # exclude all
    subgraph = context.subgraph_without(
        [
            ClickAction(id="A1", description="A1", category="A1"),
            ClickAction(id="A2", description="A2", category="A2"),
            ClickAction(id="A3", description="A3", category="A3"),
            ClickAction(id="A4", description="A4", category="A4"),
            ClickAction(id="B1", description="B1", category="B1"),
            ClickAction(id="B2", description="B2", category="B2"),
            ClickAction(id="B3", description="B3", category="B3"),
            ClickAction(id="B4", description="B4", category="B4"),
            ClickAction(id="C1", description="C1", category="C1"),
            ClickAction(id="C2", description="C2", category="C2"),
        ]
    )
    assert subgraph is None
