"""A TYPE_TEXT whose field already holds exactly the text to type is not typed: the decider is told and moves on."""

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.act import ActHistory, ObservedPage, run_act
from notte_core.act.prompts import ALREADY_FILLED
from notte_core.actions import BaseAction, ClickAction, FillAction
from notte_core.element_state import ElementState
from notte_core.observation import ExecutionResult
from notte_core.snapshot import ViewportData

from tests.act.fakes import FakeDecider


def _form(name: str, postcode: str = "") -> str:
    """A checkout form whose fields count the input events they get (`data-inputs`)."""
    return f"""<html><head><title>Checkout</title></head><body>
<form onsubmit="event.preventDefault();">
  <label>Full name <input id="name" name="name" value="{name}"></label>
  <label>Email <input id="email" name="email" type="email"></label>
  <label>Postcode <input id="postcode" name="postcode" value="{postcode}"></label>
  <button type="button" id="next">Continue</button>
</form>
<script>
  for (const field of document.querySelectorAll("input")) {{
    field.dataset.inputs = "0";
    field.addEventListener("input", () => {{ field.dataset.inputs = String(Number(field.dataset.inputs) + 1); }});
  }}
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


async def _field(session: NotteSession, element: str) -> tuple[str, int]:
    """The value of the field `element` and the input events it got."""
    value, inputs = await session.window.page.evaluate(
        "id => [document.getElementById(id).value, Number(document.getElementById(id).dataset.inputs)]", element
    )
    return value, inputs


@pytest.mark.asyncio
async def test_a_field_already_holding_the_text_is_not_typed_again(session: NotteSession) -> None:
    ids = await _open(session, _form(name="Jane Doe"))
    decider = FakeDecider(
        choices=[
            {"operation": "TYPE_TEXT", "type_text_target": ids["name"]},
            {"operation": "TYPE_TEXT", "type_text_target": ids["email"]},
        ],
        texts=["Jane Doe", "jane@example.com"],
    )
    result = await session.aact("fill the checkout form", decider=decider)

    # the name was not typed: the step went on to the email
    assert await _field(session, "name") == ("Jane Doe", 0)
    assert result.status == "executed"
    assert result.action == FillAction(id=ids["email"], value="jane@example.com")
    assert (await _field(session, "email"))[0] == "jane@example.com"
    # the decider was told the field already held the value, and the field is not offered to type in again
    told = decider.states[1].recent_actions[-1]
    assert told["kind"] == "TYPE_TEXT" and told["text"] == "Jane Doe"
    assert told["already_filled"] == ALREADY_FILLED
    assert told["page_changed"] is False and "error" not in told
    assert ids["name"] not in decider.questions[1]["type_text_target"].criteria
    assert ids["email"] in decider.questions[1]["type_text_target"].criteria


@pytest.mark.asyncio
async def test_a_field_holding_another_value_is_typed(session: NotteSession) -> None:
    ids = await _open(session, _form(name="Jane"))
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}], texts=["Jane Doe"])
    result = await session.aact("fill the checkout form", decider=decider)

    assert result.status == "executed"
    assert result.action == FillAction(id=ids["name"], value="Jane Doe")
    value, inputs = await _field(session, "name")
    assert value == "Jane Doe" and inputs > 0
    assert len(decider.states) == 1


@pytest.mark.asyncio
async def test_a_variable_the_field_already_holds_is_compared_without_reaching_the_model(
    session: NotteSession,
) -> None:
    postcode = "SW1A 1AA"
    ids = await _open(session, _form(name="", postcode=postcode))
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["postcode"]}, {"operation": "DONE"}],
        texts=["{{postcode}}"],
    )
    result = await session.aact("type {{postcode}} in the postcode", variables={"postcode": postcode}, decider=decider)

    assert result.status == "done"
    assert await _field(session, "postcode") == (postcode, 0)
    told = decider.states[1].recent_actions[-1]
    assert told["text"] == "{{postcode}}" and told["already_filled"] == ALREADY_FILLED
    # the value is compared, never sent: the model requests show the variable
    sent = [state.model_dump_json() for state in decider.states] + [c.model_dump_json() for c in decider.contexts]
    sent += [str({name: q.model_dump() for name, q in questions.items()}) for questions in decider.questions]
    assert not any(postcode in request for request in sent)


VAULT_EMAIL = "jane.private@example.test"
# the email placeholder of a vault: the vault types its secret instead
PLACEHOLDER = "user@example.org"


@pytest.mark.asyncio
@pytest.mark.parametrize("held", [VAULT_EMAIL, PLACEHOLDER])
async def test_a_vault_placeholder_is_always_typed(held: str) -> None:
    """The vault picks the secret at execution: whatever the field holds (the secret, or the placeholder's own text),
    the placeholder is typed as before, and the secret reaches no model."""
    page = ObservedPage(
        url="https://example.test/login",
        title="Login",
        description='I1[:]<input type="text" name="email"></input>\nB1[:]<button type="submit">Sign in</button>',
        actions=[FillAction(id="I1", value="<sample_value>", text_label="email"), ClickAction(id="B1")],
        viewport=ViewportData(
            scroll_x=0, scroll_y=0, viewport_width=1280, viewport_height=720, total_width=1280, total_height=720
        ),
        states={"I1": ElementState(value=held)},
        fingerprint="fp",
    )
    executed: list[BaseAction] = []

    class Driver:
        has_vault: bool = True

        def secret_replacements(self) -> dict[str, str]:
            return {VAULT_EMAIL: PLACEHOLDER}

        async def observe(self, observation: Any) -> ObservedPage:  # pyright: ignore[reportUnusedParameter]
            return page

        async def is_fresh(self, page: ObservedPage, element_id: str | None, *, focus: bool = False) -> bool:  # pyright: ignore[reportUnusedParameter]
            return True

        async def execute(self, action: BaseAction, raise_on_failure: bool, **_: Any) -> ExecutionResult:  # pyright: ignore[reportUnusedParameter]
            executed.append(action)
            now = dt.datetime.now()
            return ExecutionResult(action=action, success=True, message="Filled.", started_at=now, ended_at=now)

    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": "I1"}], texts=[PLACEHOLDER])
    result = await run_act(Driver(), decider, ActHistory(), "sign in", raise_on_failure=False)

    assert result.status == "executed"
    assert executed == [FillAction(id="I1", value=PLACEHOLDER)]
    sent = [state.model_dump_json() for state in decider.states] + [c.model_dump_json() for c in decider.contexts]
    assert not any(VAULT_EMAIL in request for request in sent)
