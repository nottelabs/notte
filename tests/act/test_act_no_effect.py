"""An action that left the page unchanged is not offered again on that same page state."""

from collections.abc import AsyncIterator
from urllib.parse import quote

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.act.runner import ActHistory, ActHistoryEntry
from notte_core.act.space import ObservedPage, build_act_space
from notte_core.actions import CheckAction, ClickAction
from notte_core.element_state import ElementState

from tests.act.fakes import FakeDecider

PAGE = """<html><head><title>Checkout</title></head><body>
<form onsubmit="event.preventDefault();">
  <label>Phone <input id="phone" name="phone"></label>
  <button type="button" id="next">Continue</button>
</form>
</body></html>"""


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        yield session


async def _ids(session: NotteSession) -> dict[str, str]:
    _ = await session.aobserve()
    return {
        node.attributes.id_name: node.id
        for node in session.snapshot.interaction_nodes()
        if node.attributes is not None and node.attributes.id_name and node.id is not None
    }


@pytest.mark.asyncio
async def test_an_action_that_changed_nothing_is_not_offered_again_on_the_same_page(session: NotteSession) -> None:
    ids = await _ids(session)
    phone, button = ids["phone"], ids["next"]
    decider = FakeDecider(
        choices=[
            # a click on an empty field: it gets the focus, the page is unchanged
            {"operation": "CLICK", "click_target": phone},
            # the button does nothing either (a form error would keep it from submitting)
            {"operation": "CLICK", "click_target": button},
            {"operation": "TYPE_TEXT", "type_text_target": phone},
            {"operation": "DONE"},
        ],
        texts=["4155550123"],
    )
    first = await session.aact("fill the phone", decider=decider)
    assert first.status == "executed"
    second = await session.aact("fill the phone", decider=decider)
    assert second.status == "executed"
    assert second.fingerprint == first.fingerprint
    # the click on the field is no longer a CLICK target; typing in it still is
    assert phone not in decider.questions[1]["click_target"].criteria
    assert button in decider.questions[1]["click_target"].criteria
    assert phone in decider.questions[1]["type_text_target"].criteria

    # neither click is offered once both changed nothing; with no CLICK target left, CLICK is not an operation
    _ = await session.aact("fill the phone", decider=decider)
    assert "click_target" not in decider.questions[2]
    assert "CLICK" not in decider.questions[2]["operation"].criteria

    # typing changed the page: on the new page state, the clicks are offered again
    _ = await session.aact("fill the phone", decider=decider)
    assert {phone, button} <= set(decider.questions[3]["click_target"].criteria)


@pytest.mark.asyncio
async def test_enter_that_changed_nothing_is_not_offered_again(session: NotteSession) -> None:
    decider = FakeDecider(choices=[{"operation": "PRESS_ENTER"}, {"operation": "DONE"}])
    pressed = await session.aact("submit", decider=decider)
    assert pressed.status == "executed"
    _ = await session.aact("submit", decider=decider)
    assert "PRESS_ENTER" not in decider.questions[1]["operation"].criteria
    # scrolls and WAIT stay offered whatever they changed: the fingerprint leaves out the scroll position
    assert "WAIT" in decider.questions[1]["operation"].criteria


def _page(states: dict[str, ElementState] | None = None) -> ObservedPage:
    return ObservedPage(
        url="https://example.test/checkout",
        title="Checkout",
        description="""_[:]Checkout
I1[:]<input type="checkbox" name="gift"></input>
B1[:]<button>Continue</button>""",
        actions=[CheckAction(id="I1", value=True, text_label="gift"), ClickAction(id="B1", text_label="Continue")],
        viewport=None,
        states={} if states is None else states,
        fingerprint="fp",
    )


def _history(*actions: tuple[str, str | None], instruction: str = "check out", error: str | None = None) -> ActHistory:
    history = ActHistory()
    for kind, target in actions:
        history.entries.append(
            ActHistoryEntry(
                action=kind,
                kind=kind,
                text=None,
                fingerprint="fp",
                page_changed=kind in ("SCROLL_DOWN", "WAIT"),
                pending=False,
                error=error,
                target=target,
                instruction=instruction,
            )
        )
    return history


def test_another_instruction_is_offered_what_changed_nothing() -> None:
    history = _history(("CLICK", "B1"), ("TYPE_TEXT", "I2"))
    assert history.no_effect(_page(), "check out") == {("CLICK", "B1"), ("CLOSE_DIALOG", "B1"), ("TYPE_TEXT", "I2")}
    assert history.no_effect(_page(), "change the email") == set()


def test_a_click_that_changed_nothing_is_not_offered_to_close_a_dialog_and_back() -> None:
    expected = {("CLICK", "B1"), ("CLOSE_DIALOG", "B1")}
    assert _history(("CLICK", "B1")).no_effect(_page(), "check out") == expected
    assert _history(("CLOSE_DIALOG", "B1")).no_effect(_page(), "check out") == expected


@pytest.mark.parametrize("key", ["PRESS_ENTER", "CLOSE_SUGGESTIONS"])
def test_a_focused_key_is_offered_again_once_another_action_ran(key: str) -> None:
    # a click can move the focus, which the fingerprint leaves out: Enter can then submit, and Escape close, the
    # focused field
    assert (key, None) not in _history((key, None), ("CLICK", "B1")).no_effect(_page(), "check out")
    # a scroll does not move the focus
    assert (key, None) in _history((key, None), ("SCROLL_DOWN", None)).no_effect(_page(), "check out")


def test_focused_keys_do_not_offer_each_other_again() -> None:
    # neither moves the focus: Enter then Escape, both changing nothing, leave both out
    no_effect = _history(("PRESS_ENTER", None), ("CLOSE_SUGGESTIONS", None)).no_effect(_page(), "check out")
    assert {("PRESS_ENTER", None), ("CLOSE_SUGGESTIONS", None)} <= no_effect


def test_a_checkbox_stays_offered_without_live_state() -> None:
    no_effect = {("CLICK", "I1"), ("CLICK", "B1")}
    # without live state, the fingerprint does not show a checkbox toggled: clicking it may have changed it
    space = build_act_space(_page(), no_effect=no_effect)
    assert set(space.targets["CLICK"]) == {"I1"}
    space = build_act_space(_page({"I1": ElementState(checked=False)}), no_effect=no_effect)
    assert "CLICK" not in space.targets


def test_an_action_that_failed_is_offered_again_unless_it_opened_a_file_chooser() -> None:
    # a click that timed out can work when tried again
    assert _history(("CLICK", "B1"), error="TimeoutError").no_effect(_page(), "check out") == set()
    assert _history(("CLICK", "B1"), error="ExecutionFailed").no_effect(_page(), "check out") == set()
    # clicking again opens the file chooser again
    chooser = _history(("CLICK", "B1"), error="FileChooserOpenedError")
    assert chooser.no_effect(_page(), "check out") == {("CLICK", "B1"), ("CLOSE_DIALOG", "B1")}


def test_a_go_back_that_moved_the_tab_back_is_offered_again() -> None:
    from dataclasses import replace

    history = _history(("GO_BACK", None))
    history.entries[0].history_index = 3
    # the tab moved back in its history: the GO_BACK did something, though the page looks the same
    assert history.no_effect(replace(_page(), history_index=2), "check out") == set()
    # it did not move
    assert history.no_effect(replace(_page(), history_index=3), "check out") == {("GO_BACK", None)}


def test_an_action_that_failed_twice_the_same_way_is_not_offered_again() -> None:
    # typing into a dropdown that is not a text field fails every time, whatever the text
    failed = _history(("TYPE_TEXT", "I13"), ("TYPE_TEXT", "I13"), error="NotteBaseError")
    assert failed.repeated_failures(_page(), "check out") == {("TYPE_TEXT", "I13")}
    # once can be bad luck
    assert _history(("TYPE_TEXT", "I13"), error="NotteBaseError").repeated_failures(_page(), "check out") == set()
    # for another instruction, or on another page, it is offered again
    assert failed.repeated_failures(_page(), "change the email") == set()
    from dataclasses import replace

    assert failed.repeated_failures(replace(_page(), fingerprint="other"), "check out") == set()


def test_failures_with_different_errors_are_offered_again() -> None:
    history = _history(("TYPE_TEXT", "I2"), error="ActionExecutionError")
    history.entries += _history(("TYPE_TEXT", "I2"), error="TimeoutError").entries
    assert history.repeated_failures(_page(), "check out") == set()


def test_a_click_that_failed_twice_is_not_offered_to_close_a_dialog_either() -> None:
    failed = _history(("CLICK", "B1"), ("CLOSE_DIALOG", "B1"), error="TimeoutError")
    assert failed.repeated_failures(_page(), "check out") == {("CLICK", "B1"), ("CLOSE_DIALOG", "B1")}


def test_a_checkbox_that_failed_twice_is_left_out_without_live_state() -> None:
    # without live state an unchanged checkbox stays offered (its toggle cannot be seen); a failed click toggled nothing
    failed = {("CLICK", "I1")}
    assert "I1" in build_act_space(_page(), no_effect=failed).targets["CLICK"]
    assert "I1" not in build_act_space(_page(), failed=failed).targets.get("CLICK", {})


EXPIRY_PAGE = """<meta charset="utf-8"><label for="month">Expiry month</label>
<div id="month" role="combobox" tabindex="0" aria-label="Expiry month">MM</div>
<button id="pay">Review order</button>"""


@pytest.mark.asyncio
async def test_typing_that_fails_twice_the_same_way_is_not_offered_again(session: NotteSession) -> None:
    # a dropdown that is not a text field: typing in it fails, whatever the text (a card expiry month)
    _ = await session.window.page.goto(f"data:text/html,{quote(EXPIRY_PAGE)}")
    month = (await _ids(session))["month"]
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": month}] * 2 + [{"operation": "DONE"}],
        texts=["12", "03"],
    )
    for _ in range(3):
        _ = await session.aact("Set the expiry month to 03", decider=decider, raise_on_failure=False)
    # once can be bad luck: offered again after the first failure
    assert month in decider.questions[1]["type_text_target"].criteria
    # twice the same way: not offered again on this page (clicking the field still is)
    third = decider.questions[2]
    assert "type_text_target" not in third or month not in third["type_text_target"].criteria
    assert month in third["click_target"].criteria
