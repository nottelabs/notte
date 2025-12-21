import pytest

from notte_browser.controller import ActionBlocklist
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData, TabsData
from notte_core.browser.dom_tree import DomNode, DomAttributes, ComputedDomAttributes, NodeType, NodeRole
from notte_core.actions import ClickAction, GotoAction, InteractionAction


def make_snapshot_with_button(button_id: str, text: str) -> BrowserSnapshot:
    # Minimal DOM tree with one interactive node
    attrs = DomAttributes.safe_init(tag_name="button", title=text, name=text)
    computed = ComputedDomAttributes()
    node = DomNode(
        id=button_id,
        type=NodeType.INTERACTION,
        role=NodeRole.BUTTON,
        text=text,
        children=[],
        attributes=attrs,
        computed_attributes=computed,
    )

    vp = ViewportData(scroll_x=0, scroll_y=0, viewport_width=800, viewport_height=600, total_width=800, total_height=600)
    tabs = [TabsData(tab_id=0, title="Test", url="https://example.com")]
    meta = SnapshotMetadata(title="Test", url="https://example.com", viewport=vp, tabs=tabs)
    return BrowserSnapshot(metadata=meta, html_content="<html></html>", a11y_tree=None, dom_node=node, screenshot=b"")


def test_blocklist_blocks_action_type():
    bl = ActionBlocklist(disallow_types={"goto"})
    action = GotoAction(url="https://example.com")
    assert bl.is_blocked(action, prev_snapshot=None) is True


def test_blocklist_allows_other_action_type():
    bl = ActionBlocklist(disallow_types={"goto"})
    action = ClickAction(id="B1")
    assert bl.is_blocked(action, prev_snapshot=None) is False


def test_blocklist_blocks_keyword_in_interaction_text():
    bl = ActionBlocklist(keywords=["delete"])
    snap = make_snapshot_with_button("B1", text="Delete account")
    action = ClickAction(id="B1")
    assert bl.is_blocked(action, prev_snapshot=snap) is True


def test_blocklist_keyword_case_insensitive():
    bl = ActionBlocklist(keywords=["DeLeTe"])  # case-insensitive
    snap = make_snapshot_with_button("B1", text="delete item")
    action = ClickAction(id="B1")
    assert bl.is_blocked(action, prev_snapshot=snap) is True


def test_blocklist_keyword_non_match():
    bl = ActionBlocklist(keywords=["delete"])  # case-insensitive
    snap = make_snapshot_with_button("B1", text="Save changes")
    action = ClickAction(id="B1")
    assert bl.is_blocked(action, prev_snapshot=snap) is False
