import asyncio

from notte_browser.session import NotteSession
from notte_core.actions import FormFillAction
from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode
from notte_core.browser.node_type import NodeType
from notte_core.browser.observation import Observation
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData
from notte_core.credentials import EMAIL, PASSWORD
from notte_core.credentials.types import ValueWithPlaceholder

from tests.mock.mock_vault import MockVault


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
        a11y_tree=None,
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


def test_session_vault_replaces_form_fill_placeholders() -> None:
    vault = MockVault({"https://example.com": {"email": "real@example.com", "password": "s3cr3t"}})
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot("https://example.com")

    action = FormFillAction(value={"email": EMAIL, "current_password": PASSWORD})
    updated = asyncio.run(session._action_with_vault(action))

    assert isinstance(updated.value["email"], ValueWithPlaceholder)
    assert updated.value["email"].get_secret_value() == "real@example.com"
    assert str(updated.value["email"]) == EMAIL
    assert isinstance(updated.value["current_password"], ValueWithPlaceholder)
    assert updated.value["current_password"].get_secret_value() == "s3cr3t"


def test_session_set_vault_enables_credential_replacement() -> None:
    """Test that set_vault() enables credential replacement for actions."""
    vault = MockVault({"https://example.com": {"email": "test@test.com", "password": "pw123"}})
    session = NotteSession()  # No vault initially
    session.snapshot = make_snapshot("https://example.com")

    # Without vault, action should pass through unchanged
    action = FormFillAction(value={"email": EMAIL})
    unchanged = asyncio.run(session._action_with_vault(action))
    assert unchanged.value["email"] == EMAIL  # Still a placeholder string

    # After setting vault, credentials should be replaced
    session.set_vault(vault)
    updated = asyncio.run(session._action_with_vault(action))
    assert isinstance(updated.value["email"], ValueWithPlaceholder)
    assert updated.value["email"].get_secret_value() == "test@test.com"


def test_session_vault_ignores_non_fill_actions() -> None:
    """Test that non-fill actions pass through without credential replacement."""
    from notte_core.actions import ClickAction, GotoAction

    vault = MockVault({"https://example.com": {"email": "test@test.com", "password": "pw123"}})
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot("https://example.com")

    # ClickAction should pass through unchanged
    click = ClickAction(id="B1")
    click_result = asyncio.run(session._action_with_vault(click))
    assert click_result is click  # Same object, unchanged

    # GotoAction should pass through unchanged
    goto = GotoAction(url="https://example.com")
    goto_result = asyncio.run(session._action_with_vault(goto))
    assert goto_result is goto  # Same object, unchanged


def test_session_vault_action_without_placeholders_passes_through() -> None:
    """Test that fill actions without credential placeholders pass through unchanged."""
    vault = MockVault({"https://example.com": {"email": "test@test.com", "password": "pw"}})
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot("https://example.com")

    # Action with regular values (not credential placeholders like EMAIL, PASSWORD)
    action = FormFillAction(value={"first_name": "John", "city": "New York"})
    result = asyncio.run(session._action_with_vault(action))
    # Should pass through unchanged since no placeholders
    assert result is action
