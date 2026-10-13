"""Public observe -> id -> execute characterization, using only local deterministic HTML.

Snapshots include the exact description, complete model_dump (selectors included), and
serialization-excluded action fields. Re-observing three times and loading a fresh document
in another session/process checks determinism without sorting away action/iframe ordering changes.
"""

from pathlib import Path

import pytest
from notte_core.errors.actions import InvalidActionError

import notte
from tests.characterization.pages import PAGES, ROOT, load
from tests.characterization.snapshots import capture_observations, check_snapshot


@pytest.mark.parametrize("fixture", PAGES)
def test_observation_is_deterministic(fixture: str, tmp_path: Path) -> None:
    # Each subprocess observes three times in each of two fresh browser sessions.
    # Comparing two processes additionally checks the complete hash-based selectors.
    first = capture_observations(fixture, tmp_path / "first.json")
    second = capture_observations(fixture, tmp_path / "second.json")
    assert first == second, f"{fixture} is not deterministic across processes"
    description, actions = first
    check_snapshot(ROOT / "snapshots" / fixture / "observe.txt", description + "\n")
    check_snapshot(ROOT / "snapshots" / fixture / "actions.json", actions)


# Independent oracles: fixture probe name, observed id, execution type, expected DOM value.
# These do not use Notte's emitted selectors to find the affected element.
CASES = [
    ("forms", "name", "I1", "fill", "Updated"),
    ("forms", "email", "I2", "fill", "updated@example.test"),
    ("forms", "password", "I3", "fill", "Updated"),
    ("forms", "notes", "I4", "fill", "Updated"),
    ("forms", "country", "I5", "select_dropdown_option", "b"),
    ("forms", "agree", "B1", "check", "true"),
    ("forms", "radio", "B2", "click", ""),
    ("forms", "other-radio", "B3", "click", ""),
    ("forms", "editor", "I6", "fill", "Updated"),
    ("forms", "save", "B4", "click", ""),
    ("forms", "icon", "B5", "click", ""),
    ("forms", "link", "L1", "click", ""),
    ("aria", "button", "B1", "click", ""),
    ("aria", "checkbox", "B2", "check", "true"),
    ("aria", "combo", "I1", "select_dropdown_option", "Banana"),
    ("aria", "apple", "O1", "click", ""),
    ("aria", "banana", "O2", "click", ""),
    ("aria", "menuitem", "B3", "click", ""),
    ("aria", "tab", "B4", "click", ""),
    ("iframes", "main-button", "B1", "click", ""),
    ("iframes", "frame-button", "B2", "click", ""),
    ("iframes", "frame-input", "I1", "fill", "Updated"),
    ("iframes", "nested-button", "B3", "click", ""),
    ("iframes", "nested-input", "I2", "fill", "Updated"),
    ("shadow", "light", "B1", "click", ""),
    ("shadow", "shadow-button", "B2", "click", ""),
    ("shadow", "shadow-input", "I1", "fill", "Updated"),
    ("shadow", "nested-button", "B3", "click", ""),
    ("shadow", "nested-input", "I2", "fill", "Updated"),
    ("shadow", "nested-check", "B4", "check", "true"),
    ("scripted", "static", "B1", "click", ""),
    ("scripted", "generated", "B2", "click", ""),
    ("scripted", "generated-input", "I1", "fill", "Updated"),
    ("scripted", "generated-select", "I2", "select_dropdown_option", "b"),
] + [
    (fixture, target, observed_id, action_type, value)
    for fixture in ("role-dialog", "native-dialog")
    for target, observed_id, action_type, value in (
        ("inside", "B2", "click", ""),
        ("outside", "B1", "click", ""),
        ("inside-input", "I2", "fill", "Updated"),
        ("outside-input", "I1", "fill", "Updated"),
    )
]


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture,target,observed_id,action_type,value", CASES, ids=[f"{c[0]}-{c[1]}" for c in CASES])
async def test_execute_by_observed_id(
    fixture: str, target: str, observed_id: str, action_type: str, value: str
) -> None:
    async with notte.Session(headless=True, viewport_width=1280, viewport_height=720) as session:
        await load(session, fixture)
        observation = await session.aobserve()
        matches = [action for action in observation.space.interaction_actions if action.id == observed_id]
        assert len(matches) == 1, [(action.id, action.text_label) for action in observation.space.interaction_actions]
        action = matches[0]
        again = await session.aobserve()
        assert [(a.id, a.text_label) for a in again.space.interaction_actions] == [
            (a.id, a.text_label) for a in observation.space.interaction_actions
        ]
        page = session.window.page
        before = await page.evaluate("characterizationState()")
        # Passing the observed action itself would bypass id resolution because it contains selectors.
        if action_type == "fill":
            result = await session.aexecute(type="fill", id=action.id, value=value)
        elif action_type == "check":
            result = await session.aexecute(type="check", id=action.id, value=True)
        elif action_type == "select_dropdown_option":
            result = await session.aexecute(type="select_dropdown_option", id=action.id, value=value)
        else:
            result = await session.aexecute(type="click", id=action.id)
        assert result.success, result.message
        events = await page.evaluate("characterizationEvents")
        after = await page.evaluate("characterizationState()")
        expected_targets = {target, "banana"} if fixture == "aria" and target == "combo" else {target}
        assert {event["target"] for event in events} == expected_targets, events
        # A click on an ARIA option updates its owning combobox, too.
        changed = expected_targets | ({"combo"} if fixture == "aria" and target in {"apple", "banana"} else set())
        assert {key: state for key, state in before.items() if key not in changed} == {
            key: state for key, state in after.items() if key not in changed
        }
        if action_type == "fill":
            assert after[target]["text" if target == "editor" else "value"] == value
        elif action_type == "check":
            assert after[target]["ariaChecked"] == "true" if fixture == "aria" else after[target]["checked"] is True
        elif action_type == "select_dropdown_option":
            assert after[target]["selected" if fixture == "aria" else "value"] == (
                "banana" if fixture == "aria" else value
            )
        elif target in {"radio", "other-radio"}:
            assert after[target]["checked"] is True
        else:
            assert [event for event in events if event["type"] == "click"] == [{"target": target, "type": "click"}]


@pytest.mark.asyncio
async def test_unknown_and_stale_ids_fail_without_affecting_other_elements() -> None:
    async with notte.Session(headless=True, viewport_width=1280, viewport_height=720) as session:
        await load(session, "scripted")
        observation = await session.aobserve()
        stale = next(
            action.id for action in observation.space.interaction_actions if action.text_label == "Generated button"
        )
        page = session.window.page
        _ = await page.evaluate("document.getElementById('generated').remove()")
        _ = await session.aobserve()
        before = await page.evaluate("characterizationState()")
        for action_id in ("B999999", stale):
            result = await session.aexecute(type="click", id=action_id, raise_on_failure=False)
            assert not result.success
            assert isinstance(result.exception, InvalidActionError)
            assert f"action '{action_id}' not found in page context" in str(result.exception)
        assert await page.evaluate("characterizationEvents") == []
        assert await page.evaluate("characterizationState()") == before


@pytest.mark.asyncio
async def test_removed_element_with_cached_id_fails_cleanly() -> None:
    """A removed element must not redirect its cached id to a surviving sibling."""
    async with notte.Session(headless=True, viewport_width=1280, viewport_height=720) as session:
        await load(session, "scripted")
        observation = await session.aobserve()
        stale = next(
            action.id for action in observation.space.interaction_actions if action.text_label == "Generated button"
        )
        page = session.window.page
        _ = await page.evaluate("document.getElementById('generated').remove()")
        before = await page.evaluate("characterizationState()")
        result = await session.aexecute(type="click", id=stale, timeout=1000, raise_on_failure=False)
        assert not result.success
        assert result.exception is not None
        assert await page.evaluate("characterizationEvents") == []
        assert await page.evaluate("characterizationState()") == before
