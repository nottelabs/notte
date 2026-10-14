"""One completed tree index serves rendering, action construction, boxes and ID resolution."""

from dataclasses import replace

import pytest
from notte_browser.action_space import build_action_space
from notte_browser.resolution import resolve
from notte_core.actions import ClickAction
from notte_core.browser.dom_tree import ComputedDomAttributes, DomNode
from notte_core.browser.node_type import NodeRole, NodeType
from notte_core.browser.observation import Observation, TimedSpan
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData
from notte_core.errors.actions import InvalidActionError
from notte_core.utils.raw_file import get_empty_dom_node

from .test_dom_actions import dialog_tree


def _snapshot(root: DomNode) -> BrowserSnapshot:
    return BrowserSnapshot(
        dom_node=root,
        html_content="",
        screenshot=b"image",
        metadata=SnapshotMetadata(
            title="Test",
            url="https://example.com",
            tabs=[],
            viewport=ViewportData(
                scroll_x=0, scroll_y=0, viewport_width=100, viewport_height=100, total_width=100, total_height=100
            ),
        ),
    )


def _dialog(name: str, children: list[DomNode], visible: bool = True) -> DomNode:
    return replace(
        DomNode.empty_root(),
        text=name,
        role=NodeRole.DIALOG,
        children=children,
        computed_attributes=ComputedDomAttributes(in_viewport=visible),
    )


@pytest.mark.parametrize("outer_visible", [True, False])
@pytest.mark.parametrize("inner_visible", [True, False])
def test_topmost_eligible_dialogs_and_action_order(outer_visible: bool, inner_visible: bool) -> None:
    first, second, third = [get_empty_dom_node(f"B{i}", f"button {i}") for i in range(1, 4)]
    inner = _dialog("inner", [second], inner_visible)
    outer = _dialog("outer", [inner], outer_visible)
    sibling = _dialog("sibling", [third])
    empty = _dialog("empty", [])
    alert = replace(_dialog("alert", []), role=NodeRole.ALERTDIALOG)
    root = replace(DomNode.empty_root(), children=[first, empty, outer, alert, sibling])
    expected = [outer, sibling] if outer_visible else [inner, sibling] if inner_visible else [sibling]
    assert [id(n) for n in root.prune_non_dialogs_if_present()] == [id(n) for n in expected]
    assert list(root.interaction_nodes_by_id) == ["B1", "B2", "B3"]
    assert [id(n) for n in root.interaction_nodes()] == [id(first), id(second), id(third)]


def test_no_eligible_dialog_falls_back_to_root() -> None:
    button = get_empty_dom_node("B1", "button")
    hidden = _dialog("hidden", [button], visible=False)
    alert = replace(_dialog("alert", [get_empty_dom_node("B2", "alert button")]), role=NodeRole.ALERTDIALOG)
    root = replace(DomNode.empty_root(), children=[_dialog("empty", []), hidden, alert])
    assert root.prune_non_dialogs_if_present()[0] is root
    # An interactive dialog can qualify on its own, without interactive children.
    interactive_dialog = replace(_dialog("self", []), id="M1", type=NodeType.INTERACTION)
    assert interactive_dialog.prune_non_dialogs_if_present()[0] is interactive_dialog


@pytest.mark.asyncio
async def test_observe_and_execute_share_one_tree_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    root = dialog_tree()
    snapshot = _snapshot(root)
    visits: list[int] = []
    is_interaction = DomNode.is_interaction

    def counted(node: DomNode) -> bool:
        visits.append(id(node))
        return is_interaction(node)

    monkeypatch.setattr(DomNode, "is_interaction", counted)
    space = build_action_space(snapshot.dom_node)
    obs = Observation.from_snapshot(snapshot, space, TimedSpan.empty())
    assert len(obs.screenshot.bboxes) == 3  # Includes the action outside the dialog.
    assert len(snapshot.interaction_nodes()) == 3
    # A fresh ID-only action uses the index; its label is descendant text, not the title attribute.
    action = await resolve(ClickAction(id="B1"), snapshot)
    assert action.text_label == "Outside"
    assert action.selectors is root.children[0].computed_attributes.selectors
    with pytest.raises(InvalidActionError):
        _ = await resolve(ClickAction(id="missing"), snapshot)
    assert visits == [id(node) for node in root.flatten()]


def test_index_lifetime_and_synthetic_download_nodes() -> None:
    root = DomNode.empty_root()
    # BrowserWindow inserts this after parsing and before exposing the snapshot.
    download = get_empty_dom_node("I0", "Download file")
    root.children.insert(0, download)
    download.set_parent(root)
    snapshot = _snapshot(root)
    assert snapshot.interaction_nodes()[0] is download
    assert snapshot.dom_node.interaction_nodes_by_id["I0"] is download
    assert download.parent is root

    replacement = dialog_tree()
    copied = snapshot.model_copy(update={"dom_node": replacement})
    assert list(copied.dom_node.interaction_nodes_by_id) == ["B1", "B2", "L1"]
    assert list(snapshot.dom_node.interaction_nodes_by_id) == ["I0"]
    snapshot.dom_node = DomNode.empty_root()
    assert not snapshot.interaction_nodes()


def test_index_is_not_serialized() -> None:
    snapshot = _snapshot(DomNode.empty_root())
    before = snapshot.model_dump()
    assert not snapshot.interaction_nodes()
    assert snapshot.dom_node.prune_non_dialogs_if_present()[0] is snapshot.dom_node
    assert snapshot.model_dump() == before
