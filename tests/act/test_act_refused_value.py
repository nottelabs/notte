"""A field that keeps its error for the goal's value, typed in several layouts, refuses that value: act stops typing
it there and tells the decider, who leaves an optional field empty and blocks on a required one."""

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.act import ActHistory, ObservedPage, prompts, run_act
from notte_core.act.runner import ActHistoryEntry
from notte_core.act.space import optional_field, same_typed_value
from notte_core.actions import FillAction
from notte_core.observation import ExecutionResult
from notte_core.snapshot import ViewportData

from tests.act.fakes import FakeDecider

INSTRUCTION = "Fill the delivery form with phone +44 7700 900123 and continue"


def _form(label: str, *, accepts: str = "", live: bool = False) -> str:
    """A delivery form whose phone field rejects every number but `accepts` (with an error shown under it), checked
    when Continue is clicked, or as it is typed (`live`). An empty field passes: the number is optional when `label`
    says so. Its name field is never checked."""
    check = "phone.addEventListener('input', check);" if live else ""
    return f"""<html><head><title>Delivery</title></head><body>
<form onsubmit="event.preventDefault();">
  <label for="name">Full name</label>
  <input id="name" name="name">
  <label for="phone">{label}</label>
  <input id="phone" name="phone" aria-describedby="phone-error">
  <p id="phone-error"></p>
  <button type="button" id="next">Continue</button>
</form>
<p id="out"></p>
<script>
  const phone = document.getElementById("phone");
  const error = document.getElementById("phone-error");
  function check() {{
    const ok = phone.value === "" || phone.value === {accepts!r};
    if (ok) {{ phone.removeAttribute("aria-invalid"); error.textContent = ""; }}
    else {{ phone.setAttribute("aria-invalid", "true"); error.textContent = 'Please enter a valid phone number (eg. "7400123456")'; }}
    return ok;
  }}
  {check}
  document.getElementById("next").addEventListener("click", () => {{
    if (check()) document.getElementById("out").textContent = "Choose a delivery option";
  }});
</script>
</body></html>"""


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        yield session


async def _open(session: NotteSession, html: str) -> dict[str, str]:
    _ = await session.window.page.goto(f"data:text/html,{quote(html)}")
    _ = await session.aobserve()
    return {
        node.attributes.id_name: node.id
        for node in session.snapshot.interaction_nodes()
        if node.attributes is not None and node.attributes.id_name and node.id is not None
    }


def _element(decider: FakeDecider, call: int, element_id: str) -> dict[str, Any]:
    return next(e for e in decider.states[call].elements if e["index"] == element_id)


def _typable(decider: FakeDecider, call: int) -> set[str]:
    question = decider.questions[call].get("type_text_target")
    return set() if question is None else set(question.criteria)


async def _type_and_continue(session: NotteSession, ids: dict[str, str], numbers: list[str]) -> FakeDecider:
    """Types each of `numbers` in the phone field and clicks Continue after each, one act() call per action."""
    phone, continue_ = {"operation": "TYPE_TEXT", "type_text_target": ids["phone"]}, {"click_target": ids["next"]}
    decider = FakeDecider(
        choices=[step for _ in numbers for step in (phone, {"operation": "CLICK", **continue_})], texts=list(numbers)
    )
    for _ in range(2 * len(numbers)):
        result = await session.aact(INSTRUCTION, decider=decider)
        assert result.status == "executed"
    return decider


@pytest.mark.asyncio
async def test_a_required_field_that_refuses_the_value_in_every_layout_is_not_typed_again(
    session: NotteSession,
) -> None:
    ids = await _open(session, _form("Phone"))
    decider = await _type_and_continue(session, ids, ["07700900123", "7700900123"])
    # one rejection is retried in another layout: the field is still offered after the first Continue
    assert ids["phone"] in _typable(decider, 2)
    assert "refused" not in _element(decider, 2, ids["phone"])

    decider.choices.append({"operation": "BLOCKED"})
    result = await session.aact(INSTRUCTION, decider=decider, raise_on_failure=False)

    # the same digits rejected twice: the decider is told the page refuses them; the field stays offered, for another
    # value the goal could give
    assert ids["phone"] in _typable(decider, 4)
    assert _element(decider, 4, ids["phone"])["refused"] == prompts.REFUSED_REQUIRED
    assert result.status == "blocked"
    assert len(decider.contexts) == 2


@pytest.mark.asyncio
async def test_a_field_checked_as_it_is_typed_refuses_the_value_after_two_rejections(session: NotteSession) -> None:
    """Typed again and again with nothing in between: each text is rejected once the next is typed over its error."""
    ids = await _open(session, _form("Phone", live=True))
    phone = {"operation": "TYPE_TEXT", "type_text_target": ids["phone"]}
    decider = FakeDecider(
        choices=[phone, phone, phone, {"operation": "BLOCKED"}], texts=["07700900123", "7700900123", "+447700900123"]
    )
    for _ in range(3):
        assert (await session.aact(INSTRUCTION, decider=decider)).status == "executed"
    assert ids["phone"] in _typable(decider, 2)
    result = await session.aact(INSTRUCTION, decider=decider, raise_on_failure=False)

    assert _element(decider, 3, ids["phone"])["refused"] == prompts.REFUSED_REQUIRED
    assert result.status == "blocked"


@pytest.mark.asyncio
async def test_an_optional_field_that_refuses_the_value_is_emptied_and_left_empty(session: NotteSession) -> None:
    ids = await _open(session, _form("Telephone number (optional)"))
    decider = await _type_and_continue(session, ids, ["07700900123", "+44 7700 900123"])
    decider.choices += [
        {"operation": "TYPE_TEXT", "type_text_target": ids["phone"]},
        {"operation": "CLICK", "click_target": ids["next"]},
    ]

    # still holding the refused number: offered only to empty it, without asking the writer
    result = await session.aact(INSTRUCTION, decider=decider)
    assert _element(decider, 4, ids["phone"])["refused"] == prompts.REFUSED_CLEAR
    assert result.action == FillAction(id=ids["phone"], value="")
    assert len(decider.contexts) == 2
    assert await session.window.page.input_value("#phone") == ""

    # empty: left so, and the form goes on
    result = await session.aact(INSTRUCTION, decider=decider)
    assert ids["phone"] not in _typable(decider, 5)
    assert _element(decider, 5, ids["phone"])["refused"] == prompts.REFUSED_OPTIONAL
    assert result.status == "executed" and result.target == ids["next"]
    assert await session.window.page.text_content("#out") == "Choose a delivery option"


@pytest.mark.asyncio
async def test_a_value_accepted_in_its_second_layout_is_not_refused(session: NotteSession) -> None:
    """The page wants the national number without its leading 0: the second layout is accepted. Its old error still
    shows after typing it, until Continue checks the field again."""
    ids = await _open(session, _form("Phone", accepts="7700900123"))
    decider = await _type_and_continue(session, ids, ["07700900123", "7700900123"])
    assert await session.window.page.text_content("#out") == "Choose a delivery option"
    # the second number was typed over the first one's error: not refused before Continue checked it
    assert "refused" not in _element(decider, 3, ids["phone"])

    decider.choices.append({"operation": "DONE"})
    result = await session.aact(INSTRUCTION, decider=decider)
    assert result.status == "done"
    assert ids["phone"] in _typable(decider, 4)
    assert "refused" not in _element(decider, 4, ids["phone"])


@pytest.mark.asyncio
async def test_an_accepted_layout_followed_by_another_field_is_not_refused_before_continue(
    session: NotteSession,
) -> None:
    """A form checked on Continue: the second layout is accepted, but its field keeps the first one's error while the
    name is typed. Only Continue checks it: the field is not refused before."""
    ids = await _open(session, _form("Phone", accepts="7700900123"))
    phone, name = (
        {"operation": "TYPE_TEXT", "type_text_target": ids["phone"]},
        {"operation": "TYPE_TEXT", "type_text_target": ids["name"]},
    )
    decider = FakeDecider(
        choices=[
            phone,
            {"operation": "CLICK", "click_target": ids["next"]},
            phone,
            name,
            {"operation": "CLICK", "click_target": ids["next"]},
        ],
        texts=["07700900123", "7700900123", "Jamie Burke"],
    )
    for _ in range(5):
        assert (await session.aact(INSTRUCTION, decider=decider)).status == "executed"

    # typing the name ran between the accepted layout and Continue, with the old error still shown
    assert "refused" not in _element(decider, 4, ids["phone"])
    assert await session.window.page.text_content("#out") == "Choose a delivery option"


BACKUP = "Fill the delivery form with phone +44 7700 900123 (if the page refuses it, use 020 7946 0123) and continue"


@pytest.mark.asyncio
async def test_a_backup_value_the_goal_gives_is_typed_after_the_first_is_refused(session: NotteSession) -> None:
    ids = await _open(session, _form("Phone", accepts="02079460123"))
    phone, continue_ = {"operation": "TYPE_TEXT", "type_text_target": ids["phone"]}, {"click_target": ids["next"]}
    decider = FakeDecider(
        choices=[step for _ in range(3) for step in (phone, {"operation": "CLICK", **continue_})],
        texts=["07700900123", "7700900123", "02079460123"],
    )
    for _ in range(4):
        assert (await session.aact(BACKUP, decider=decider)).status == "executed"

    # refused: the field stays offered, and the goal's other number is typed in it
    result = await session.aact(BACKUP, decider=decider)
    assert _element(decider, 4, ids["phone"])["refused"] == prompts.REFUSED_REQUIRED
    assert result.action == FillAction(id=ids["phone"], value="02079460123")
    # the writer was told which number the page refused, so it writes the goal's backup
    assert "07700900123" in decider.contexts[-1].field["refused"]
    assert (await session.aact(BACKUP, decider=decider)).status == "executed"
    assert await session.window.page.text_content("#out") == "Choose a delivery option"


@pytest.mark.asyncio
async def test_the_refused_value_written_again_in_another_layout_is_not_typed(session: NotteSession) -> None:
    ids = await _open(session, _form("Phone"))
    decider = await _type_and_continue(session, ids, ["07700900123", "7700900123"])
    decider.choices += [{"operation": "TYPE_TEXT", "type_text_target": ids["phone"]}, {"operation": "BLOCKED"}]
    decider.texts.append("+44 7700 900123")

    result = await session.aact(INSTRUCTION, decider=decider, raise_on_failure=False)

    # written again in a third layout: not typed, the field left, and the decider stops
    assert await session.window.page.input_value("#phone") == "7700900123"
    assert ids["phone"] not in _typable(decider, 5)
    assert result.status == "blocked"


@pytest.mark.asyncio
async def test_a_value_refused_before_the_writer_switched_to_another_is_not_typed_again(session: NotteSession) -> None:
    """Checked as it is typed: the goal's number rejected in two layouts, then its backup accepted. The first number
    is refused though it is not the last text typed: written again, it is not typed. The field holding the accepted
    backup is not marked refused."""
    ids = await _open(session, _form("Phone", accepts="02079460123", live=True))
    phone = {"operation": "TYPE_TEXT", "type_text_target": ids["phone"]}
    decider = FakeDecider(
        choices=[phone, phone, phone, phone, {"operation": "DONE"}],
        texts=["07700900123", "7700900123", "02079460123", "+44 7700 900123"],
    )
    for _ in range(3):
        assert (await session.aact(BACKUP, decider=decider)).status == "executed"
    assert await session.window.page.input_value("#phone") == "02079460123"

    # the refused number, written again in a third layout: not typed over the accepted backup
    result = await session.aact(BACKUP, decider=decider, raise_on_failure=False)
    assert "refused" not in _element(decider, 3, ids["phone"])
    assert "07700900123" in decider.contexts[-1].field["refused"]
    assert await session.window.page.input_value("#phone") == "02079460123"
    assert result.status == "done"


@pytest.mark.asyncio
async def test_a_written_value_refused_before_it_was_typed_is_written_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """The page changes between writing the number and typing it, and its next observation records the number as
    refused: the cached number is not reused, the writer writes again knowing the refusal, and the backup is typed."""
    page = ObservedPage(
        url="https://example.test/delivery",
        title="Delivery",
        description='I1[:]<input type="text" name="phone"></input>\nB1[:]<button type="button">Continue</button>',
        actions=[FillAction(id="I1", value="<sample_value>", text_label="Phone")],
        viewport=ViewportData(
            scroll_x=0, scroll_y=0, viewport_width=1280, viewport_height=720, total_width=1280, total_height=720
        ),
        states={},
        fingerprint="fp",
    )
    executed: list[Any] = []
    looks = 0

    class Driver:
        has_vault: bool = False

        def secret_replacements(self) -> dict[str, str]:
            return {}

        async def observe(self, observation: Any) -> ObservedPage:  # pyright: ignore[reportUnusedParameter]
            nonlocal looks
            looks += 1
            return page

        async def is_fresh(self, page: ObservedPage, element_id: str | None, *, focus: bool = False) -> bool:  # pyright: ignore[reportUnusedParameter]
            return looks > 1

        async def execute(self, action: Any, raise_on_failure: bool, **_: Any) -> ExecutionResult:  # pyright: ignore[reportUnusedParameter]
            executed.append(action)
            now = dt.datetime.now()
            return ExecutionResult(action=action, success=True, message="Filled.", started_at=now, ended_at=now)

    # the refusal is recorded by the second observation only
    def refused_values(self: ActHistory, page: ObservedPage, instruction: str, variables: Any) -> dict[str, list[str]]:  # pyright: ignore[reportUnusedParameter]
        return {"I1": ["07700900123"]} if looks > 1 else {}

    monkeypatch.setattr(ActHistory, "refused_values", refused_values)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": "I1"}] * 2, texts=["07700900123", "02079460123"]
    )
    result = await run_act(Driver(), decider, ActHistory(), BACKUP, raise_on_failure=False)

    assert result.status == "executed"
    assert executed == [FillAction(id="I1", value="02079460123")]
    assert len(decider.contexts) == 2 and "07700900123" in decider.contexts[1].field["refused"]


@pytest.mark.asyncio
async def test_typing_zero_does_not_break_the_next_call(session: NotteSession) -> None:
    """A value with no letters or digits left once compared ("0": leading zeros are dropped) never compares equal to
    itself: it is never refused, and observing the page again after typing it works."""
    ids = await _open(session, _form("Quantity"))
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["phone"]}, {"operation": "DONE"}], texts=["0"]
    )
    assert (await session.aact("Set the quantity to 0", decider=decider)).status == "executed"
    assert (await session.aact("Set the quantity to 0", decider=decider)).status == "done"


def test_a_fill_that_failed_is_not_submitted() -> None:
    """A Continue after a fill that failed submits nothing of it: it never counts as a text the page rejected."""
    history = ActHistory()
    typed = ActHistoryEntry(action="Phone", kind="TYPE_TEXT", text="07700900123", fingerprint="fp", pending=False)
    failed = ActHistoryEntry(
        action="Phone", kind="TYPE_TEXT", text="7700900123", fingerprint="fp", pending=False, error="ExecutionFailed"
    )
    history.entries.extend([typed, failed])
    history.acted("CLICK", None)
    assert typed.submitted and not failed.submitted


def test_text_typed_in_a_field_does_not_make_it_optional() -> None:
    """A required textarea holding "optional" (a delivery note the buyer wrote) is still required; its label decides."""

    def page(description: str) -> ObservedPage:
        return ObservedPage(
            url="https://example.test/checkout",
            title="Checkout",
            description=description,
            actions=[FillAction(id="I1", value="<sample_value>")],
            viewport=ViewportData(
                scroll_x=0, scroll_y=0, viewport_width=1280, viewport_height=720, total_width=1280, total_height=720
            ),
            states={},
            fingerprint="fp",
        )

    assert not optional_field(
        page('I1[:]<textarea name="note">leave it at the door, signature optional</textarea>'), "I1"
    )
    assert optional_field(page('I1[:]<textarea name="note" placeholder="Delivery note (optional)"></textarea>'), "I1")


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("07700900123", "7700900123", True),
        ("+44 7700 900123", "07700-900123", True),
        ("0044 7700900123", "7700900123", True),
        ("+447700900123", "+33 7700900123", False),
        ("7700900123", "7700900124", False),
        ("07700900123", "Burke", False),
        ("jane@example.com", " Jane@Example.com ", True),
        ("SW1A 1AA", "sw1a-1aa", True),
        ("jane@example.com", "jane@example.org", False),
        ("", "", False),
    ],
)
def test_same_typed_value(a: str, b: str, same: bool) -> None:
    assert same_typed_value(a, b) is same
