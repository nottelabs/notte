"""`goto` accepts a `wait_until` navigation event and omits it from the wire when unset."""

import pytest
from notte_browser.session import NotteSession
from notte_core.actions import GotoAction
from notte_core.actions.typedicts import action_dict_to_base_action
from pydantic import ValidationError


def test_goto_action_defaults_to_no_wait_until_and_omits_it_when_dumped() -> None:
    action = GotoAction(url="https://example.com")

    assert action.wait_until is None
    # older API builds reject unknown fields, so an unset value must not be sent
    assert "wait_until" not in action.model_dump(exclude_none=True)


def test_goto_action_accepts_the_playwright_events_only() -> None:
    assert GotoAction(url="https://example.com", wait_until="commit").wait_until == "commit"
    assert (
        action_dict_to_base_action(
            {"type": "goto", "url": "https://example.com", "wait_until": "domcontentloaded"}
        ).wait_until
        == "domcontentloaded"
    )  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        _ = GotoAction(url="https://example.com", wait_until="eventually")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_goto_with_commit_is_enough_for_a_same_origin_fetch() -> None:
    async with NotteSession(headless=True) as session:
        result = await session.aexecute(type="goto", url="https://www.example.com/", wait_until="commit")
        assert result.success

        response = await session.afetch("/")

        assert response.status_code == 200
        assert "Example Domain" in response.text
