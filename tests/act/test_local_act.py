"""`NotteSession.act()` / `choose()` / `check()` end to end on a local page, with a scripted decider."""

import asyncio
import html
import json
from collections.abc import AsyncIterator, Mapping
from typing import Any
from urllib.parse import quote

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.act import (
    Answers,
    DecisionState,
    InvalidDecisionError,
    NoActionFoundError,
    Question,
    WriteContext,
    prompts,
)
from notte_core.actions import CheckAction, FillAction, SelectDropdownOptionAction, WaitAction
from notte_core.errors import ActionExecutionError

from tests.act.fakes import FakeDecider

PAGE = """<html><head><title>Signup</title></head><body>
<form onsubmit="event.preventDefault(); document.getElementById('out').textContent = 'sent';">
  <label>Name <input id="name" name="name"></label>
  <label>Country <select id="country" name="country">
    <option value="">Choose</option><option value="fr">France</option><option value="us">United States</option>
  </select></label>
  <input type="checkbox" id="terms" name="terms" aria-label="Accept the terms">
  <button type="submit">Subscribe</button>
</form>
<p id="out"></p>
</body></html>"""


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        yield session


async def _ids(session: NotteSession) -> dict[str, str]:
    """Action id by element id attribute (`name` -> `I1`)."""
    _ = await session.aobserve()
    ids: dict[str, str] = {}
    for node in session.snapshot.interaction_nodes():
        if node.attributes is not None and node.attributes.id_name:
            ids[node.attributes.id_name] = node.id
    return ids


@pytest.mark.asyncio
async def test_act_types_text_with_variables_substituted_after_the_model(session: NotteSession) -> None:
    ids = await _ids(session)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}], texts=["{{first}} Doe"]
    )
    result = await session.aact("Sign up as {{first}} Doe", variables={"first": "Jane"}, decider=decider)

    assert result.status == "executed" and result.success
    assert isinstance(result.action, FillAction) and result.action.value == "Jane Doe"
    # the result and the model only see the template
    assert result.value == "{{first}} Doe"
    assert decider.contexts[0].variables == ["first"]
    assert "Jane" not in decider.contexts[0].model_dump_json()
    assert await session.window.page.input_value("#name") == "Jane Doe"
    assert result.timings.decide_ms >= 0 and result.timings.total_ms >= result.timings.execute_ms
    assert result.model == "fake"


@pytest.mark.asyncio
async def test_act_selects_an_option_and_checks_a_box(session: NotteSession) -> None:
    ids = await _ids(session)
    decider = FakeDecider(
        choices=[
            # "Choose" is selected on load, so the targets are France (1) and United States (2)
            {"operation": "SELECT", "select_target": f"{ids['country']}:1"},
            {"operation": "CLICK", "click_target": ids["terms"]},
            {"operation": "DONE"},
        ]
    )
    selected = await session.aact("from France", decider=decider)
    assert isinstance(selected.action, SelectDropdownOptionAction) and selected.action.value == "fr"
    assert await session.window.page.input_value("#country") == "fr"

    checked = await session.aact("accept the terms", decider=decider)
    assert isinstance(checked.action, CheckAction) and checked.action.value is True
    assert await session.window.page.is_checked("#terms")

    # the live state reaches the decider: the select shows its new value, the history the last action
    state = decider.states[1]
    country = next(e for e in state.elements if e["index"] == ids["country"])
    assert country["value"] == "France"
    assert state.recent_actions[-1]["kind"] == "SELECT" and state.recent_actions[-1]["page_changed"] is True

    # a toggle says which way it went (a "CLICK" on a checkbox can uncheck it)
    _ = await session.aact("accept the terms", decider=decider)
    assert decider.states[2].recent_actions[-1]["action"] == "Check Accept the terms"


@pytest.mark.asyncio
async def test_done_blocked_and_low_confidence(session: NotteSession) -> None:
    done = await session.aact("nothing", decider=FakeDecider(choices=[{"operation": "DONE"}]))
    assert done.status == "done" and done.action is None and done.success

    with pytest.raises(NoActionFoundError) as error:
        _ = await session.aact("impossible", decider=FakeDecider(choices=[{"operation": "BLOCKED"}]))
    assert error.value.result is not None and error.value.result.status == "blocked"

    blocked = await session.aact(
        "impossible", raise_on_failure=False, decider=FakeDecider(choices=[{"operation": "BLOCKED"}])
    )
    assert blocked.status == "blocked" and not blocked.success

    ids = await _ids(session)
    unsure = FakeDecider(choices=[{"operation": "CLICK", "click_target": ids["terms"]}], confidence=0.3)
    low = await session.aact("accept", min_confidence=0.5, raise_on_failure=False, decider=unsure)
    assert low.status == "blocked" and "min_confidence" in (low.message or "")
    assert not await session.window.page.is_checked("#terms")


@pytest.mark.asyncio
async def test_dry_run_proposes_without_executing(session: NotteSession) -> None:
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}], texts=["Jane"])
    result = await session.aact("type Jane", dry_run=True, decider=decider)
    assert result.status == "proposed" and result.execution is None and result.success
    assert await session.window.page.input_value("#name") == ""
    assert result.action is not None
    _ = await session.aexecute(result.action)
    assert await session.window.page.input_value("#name") == "Jane"


@pytest.mark.asyncio
async def test_page_changing_under_the_decision_is_stale_and_text_is_reused(session: NotteSession) -> None:
    ids = await _ids(session)
    page = session.window.page
    counter = {"n": 0}

    async def type_while_deciding() -> None:
        counter["n"] += 1
        await page.fill("#name", f"changed {counter['n']}")

    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}] * 2,
        texts=["Jane"],
        on_choose=type_while_deciding,
    )
    result = await session.aact("type Jane", raise_on_failure=False, decider=decider)

    assert result.status == "stale" and result.execution is None
    # decided twice (the first decision is never reused), wrote once
    assert len(decider.states) == 2 and len(decider.contexts) == 1
    assert await page.input_value("#name") == "changed 2"


@pytest.mark.asyncio
async def test_invalid_answers_execute_nothing(session: NotteSession) -> None:
    class Broken(FakeDecider):
        async def choose(self, state, questions):  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
            answers = await super().choose(state, questions)  # pyright: ignore[reportUnknownArgumentType]
            answers.answers["operation"].probabilities["CLICK"] = 0.95
            return answers

    # asked again once, then raised (nothing executed)
    broken = Broken(choices=[{"operation": "DONE"}] * 2)
    with pytest.raises(InvalidDecisionError):
        _ = await session.aact("anything", decider=broken)
    assert len(broken.states) == 2

    # raise_on_failure=False: blocked, not raised
    result = await session.aact("anything", decider=Broken(choices=[{"operation": "DONE"}] * 2), raise_on_failure=False)
    assert result.status == "blocked" and result.execution is None and "invalid" in (result.message or "")


@pytest.mark.asyncio
async def test_an_invalid_answer_is_asked_again_once(session: NotteSession) -> None:
    class BrokenOnce(FakeDecider):
        async def choose(self, state, questions):  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
            answers = await super().choose(state, questions)  # pyright: ignore[reportUnknownArgumentType]
            if len(self.states) == 1:
                answers.answers.pop("operation")
            return answers

    decider = BrokenOnce(choices=[{"operation": "DONE"}] * 2)
    result = await session.aact("anything", decider=decider)
    assert result.status == "done" and len(decider.states) == 2


@pytest.mark.asyncio
async def test_an_invalid_field_value_is_asked_again_once(session: NotteSession) -> None:
    ids = await _ids(session)

    class BadWriter(FakeDecider):
        async def write(self, context: WriteContext) -> str | None:
            self.contexts.append(context)
            raise InvalidDecisionError("the field writer returned no valid field value; nothing typed")

    decider = BadWriter(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}])
    result = await session.aact("Type Jane", decider=decider, raise_on_failure=False)
    assert result.status == "blocked" and result.execution is None and len(decider.contexts) == 2
    assert await session.window.page.input_value("#name") == ""


@pytest.mark.asyncio
async def test_choose_and_check(session: NotteSession) -> None:
    decider = FakeDecider(choices=[{"answer": "Signup"}, {"answer": "NO"}])
    choice = await session.achoose("Which page is this?", ["Signup", "Login"], decider=decider)
    assert choice.choice == "Signup" and choice.probabilities == {"Signup": 0.9, "Login": pytest.approx(0.1)}

    probability = await session.acheck("Is the form sent?", decider=decider)
    assert probability == pytest.approx(0.1)
    assert set(decider.questions[1]["answer"].criteria) == {"YES", "NO"}
    assert "Subscribe" in decider.states[1].page.text

    with pytest.raises(ValueError):
        _ = await session.achoose("?", ["only one"], decider=decider)


@pytest.mark.asyncio
@pytest.mark.parametrize("private", ["jane.private@example.test", "private-" * 40])
async def test_variables_stay_masked_in_later_model_requests(session: NotteSession, private: str) -> None:
    ids = await _ids(session)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}] * 2
        + [{"answer": "YES"}, {"answer": "a"}],
        texts=["{{private}}", "public"],
    )
    _ = await session.aact("Type {{private}}", variables={"private": private}, decider=decider)
    assert await session.window.page.input_value("#name") == private
    # Echoed page text must be protected too, including for calls without variables.
    await session.window.page.eval_on_selector("#out", "(el, text) => el.textContent = text", private)
    _ = await session.aact("Replace the name", decider=decider)
    _ = await session.acheck("Is the form visible?", decider=decider)
    _ = await session.achoose("Pick", {"a": "one", "b": "two"}, decider=decider)
    for payload in [*decider.states, *decider.contexts]:
        assert private[:200] not in payload.model_dump_json()
    for questions in decider.questions:
        assert private[:200] not in json.dumps({key: q.model_dump() for key, q in questions.items()})
    assert any(e.get("value") == "{{private}}" for e in decider.states[1].elements)
    assert decider.contexts[1].field["value"] == "{{private}}"
    assert await session.window.page.input_value("#name") == "public"


@pytest.mark.asyncio
@pytest.mark.parametrize("private", ["id_digit", "select", "input", "checkbox", "fr"])
async def test_private_values_do_not_change_action_choices(session: NotteSession, private: str) -> None:
    ids = await _ids(session)
    if private == "id_digit":
        private = ids["country"][1:]
    decider = FakeDecider(
        choices=[
            {"operation": "SELECT", "select_target": f"{ids['country']}:1"},
            {"operation": "SELECT", "select_target": f"{ids['country']}:2"},
        ]
    )
    first = await session.aact("Choose France", variables={"private": private}, decider=decider)
    assert first.success and await session.window.page.input_value("#country") == "fr"
    # Remembered values must not change later calls' structure either.
    second = await session.aact("Choose United States", decider=decider)
    assert second.success and await session.window.page.input_value("#country") == "us"
    for state, questions in zip(decider.states, decider.questions):
        elements = {e["index"]: e for e in state.elements}
        assert elements[ids["country"]]["role"] == "select"
        assert elements[ids["name"]]["role"] == "textbox"
        assert elements[ids["terms"]]["role"] == "checkbox"
        assert "SELECT" in questions["operation"].criteria
        assert ids["country"] not in questions["type_text_target"].criteria
        assert f"[{ids['country']}]" in state.page.text


@pytest.mark.asyncio
async def test_choose_and_check_receive_live_form_state(session: NotteSession) -> None:
    page = session.window.page
    await page.fill("#name", "Jane")
    await page.check("#terms")
    _ = await page.select_option("#country", "fr")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"answer": "fr"}, {"answer": "YES"}])
    _ = await session.achoose("Which country?", {"fr": "France", "us": "USA"}, decider=decider)
    _ = await session.acheck("Are the terms accepted?", decider=decider)
    for state in decider.states:
        elements = {e["index"]: e for e in state.elements}
        assert elements[ids["name"]]["value"] == "Jane"
        assert elements[ids["country"]]["value"] == "France"
        assert elements[ids["terms"]]["checked"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("navigate", [False, True])
async def test_supplied_observation_is_refreshed_before_act(session: NotteSession, navigate: bool) -> None:
    old = await session.aobserve()
    html = PAGE.replace("Subscribe", "Delete account")
    if navigate:
        _ = await session.window.page.goto(f"data:text/html,{quote(html)}")
    else:
        await session.window.page.set_content(html)
    # Simulate another caller replacing the session snapshot, too.
    _ = await session.aobserve()
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("Review the button", observation=old, decider=decider)
    assert "Delete account" in decider.states[0].page.text
    assert "Subscribe" not in decider.states[0].page.text
    assert decider.states[0].page.url == session.window.page.url


@pytest.mark.asyncio
async def test_act_selects_a_noneditable_custom_dropdown(session: NotteSession) -> None:
    from tests.browser.test_controller_select_dropdown import PAGE as DROPDOWN_PAGE

    _ = await session.window.page.goto(f"data:text/html,{quote(DROPDOWN_PAGE)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["fruit"]}], texts=["Banana"])
    result = await session.aact("Choose Banana", decider=decider)
    assert result.success and isinstance(result.action, SelectDropdownOptionAction)
    assert await session.window.page.get_attribute("#fruit", "data-selected") == "b"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["href", "option_value", "option_disabled", "optgroup_disabled", "long_value"])
async def test_freshness_detects_action_relevant_changes(session: NotteSession, change: str) -> None:
    page = session.window.page
    await page.eval_on_selector(
        "form",
        "el => { el.insertAdjacentHTML('beforeend', '<a id=link href=#first>Continue</a>'); "
        "const select = document.getElementById('country'); "
        "const group = document.createElement('optgroup'); group.label = 'Choices'; "
        "group.append(select.options[1]); select.append(group); }",
    )
    await page.fill("#name", "x" * 400 + "initial")
    ids = await _ids(session)
    count = 0

    async def mutate() -> None:
        nonlocal count
        count += 1
        if change == "href":
            await page.eval_on_selector("#link", "(el, n) => el.href = '#changed' + n", count)
        elif change == "long_value":
            await page.fill("#name", "x" * 400 + str(count))
        else:
            script = {
                "option_value": "(el, n) => el.value = 'changed' + n",
                "option_disabled": "el => el.disabled = !el.disabled",
                "optgroup_disabled": "el => el.parentElement.disabled = !el.parentElement.disabled",
            }[change]
            await page.eval_on_selector("#country optgroup option", script, count)

    target = ids["link"] if change == "href" else ids["name"] if change == "long_value" else ids["country"]
    choices = {"operation": "CLICK", "click_target": target}
    if change.startswith("option") or change.startswith("optgroup"):
        choices = {"operation": "SELECT", "select_target": f"{target}:1"}
    decider = FakeDecider(choices=[choices] * 2, on_choose=mutate)
    result = await session.aact("Use the target", decider=decider, raise_on_failure=False)
    assert result.status == "stale" and result.execution is None


def test_sync_act_and_session_decider_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_browser import session as session_module

    decider = FakeDecider(choices=[{"operation": "DONE"}, {"answer": "YES"}])
    resolved: list[int] = []

    def fake_default() -> FakeDecider:
        resolved.append(1)
        return decider

    monkeypatch.setattr(session_module, "default_decider", fake_default)
    with NotteSession(headless=True) as session:
        _ = asyncio.run(session.window.page.goto(f"data:text/html,{quote(PAGE)}"))
        assert session.act("nothing to do").status == "done"
        assert session.check("Is there a form?") == pytest.approx(0.9)
    # resolved once, then cached on the session
    assert resolved == [1]


@pytest.mark.asyncio
async def test_controls_run_when_element_signatures_are_unavailable(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from notte_browser.session import LocalActDriver
    from notte_core.act.freshness import Signatures

    async def unavailable(self: LocalActDriver, xpaths: dict[str, str]) -> Signatures:  # pyright: ignore[reportUnusedParameter]
        return Signatures(None)

    # the signature script failed after observing: the re-check compares a new snapshot instead
    monkeypatch.setattr(LocalActDriver, "_read_signatures", unavailable)
    decider = FakeDecider(choices=[{"operation": "PRESS_ENTER"}] * 2)
    result = await session.aact("submit", decider=decider)
    assert result.status == "executed" and len(decider.states) == 1


@pytest.mark.asyncio
async def test_a_page_changed_before_the_signature_baseline_is_decided_again(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from notte_browser.session import LocalActDriver

    read = LocalActDriver._read_signatures  # pyright: ignore[reportPrivateUsage]
    calls = {"n": 0}

    async def change_then_read(self: LocalActDriver, xpaths: dict[str, str]):  # pyright: ignore[reportUnknownParameterType]
        calls["n"] += 1
        if calls["n"] == 1:
            # the page changes after the snapshot, before the baseline is read
            await session.window.page.eval_on_selector("button", "el => el.textContent = 'Delete account'")
        return await read(self, xpaths)  # pyright: ignore[reportUnknownVariableType]

    monkeypatch.setattr(LocalActDriver, "_read_signatures", change_then_read)
    observation = await session.aobserve()
    button = next(a.id for a in observation.space.interaction_actions if (a.text_label or "") == "Subscribe")
    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": button}] * 2)
    result = await session.aact("subscribe", decider=decider, raise_on_failure=False)
    # the decision taken on "Subscribe" is not executed on "Delete account": it is taken again
    assert len(decider.states) == 2
    assert "Delete account" in decider.states[1].page.text
    assert result.status == "executed"


def test_session_closes_the_decider_it_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_browser import session as session_module

    class Closable(FakeDecider):
        closed: int = 0

        def close(self) -> None:
            self.closed += 1

    owned = Closable(choices=[{"operation": "DONE"}])
    passed = Closable(choices=[{"operation": "DONE"}])
    monkeypatch.setattr(session_module, "default_decider", lambda: owned)
    with NotteSession(headless=True) as session:
        _ = asyncio.run(session.window.page.goto(f"data:text/html,{quote(PAGE)}"))
        _ = session.act("nothing to do")
        _ = session.act("nothing to do", decider=passed)
    assert owned.closed == 1 and passed.closed == 0


@pytest.mark.asyncio
async def test_act_clears_a_field(session: NotteSession) -> None:
    await session.window.page.fill("#name", "Jane")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}], texts=[""])
    result = await session.aact("clear the name", decider=decider)
    assert result.status == "executed" and await session.window.page.input_value("#name") == ""


@pytest.mark.asyncio
async def test_a_writer_refusal_blocks_the_step(session: NotteSession) -> None:
    from notte_core.errors import ContentFilterError

    class Refusing(FakeDecider):
        async def write(self, context):  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
            raise ContentFilterError("writer and decider", "both text models refused")

    ids = await _ids(session)
    choices = [{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}]
    with pytest.raises(NoActionFoundError, match="refused") as error:
        _ = await session.aact("type Ada Lovelace", decider=Refusing(choices=list(choices)))
    assert isinstance(error.value.__cause__, ContentFilterError)
    blocked = await session.aact("type Ada Lovelace", raise_on_failure=False, decider=Refusing(choices=list(choices)))
    assert blocked.status == "blocked" and "content-policy" in (blocked.message or "")
    assert await session.window.page.input_value("#name") == ""


@pytest.mark.asyncio
async def test_accessible_labels_reach_the_decider_and_the_writer(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOTTE_ACT_LABELS", "accessible")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}], texts=["{{who}}"])
    result = await session.aact("Sign up as {{who}}", variables={"who": "Subscribe"}, decider=decider)

    assert result.success and await session.window.page.input_value("#name") == "Subscribe"
    state = decider.states[0]
    labels = {e["index"]: e["label"] for e in state.elements}
    assert labels[ids["name"]] == "Name" and labels[ids["terms"]] == "Accept the terms"
    assert labels[ids["country"]] == "Country"
    assert f"[{ids['name']}] Name" in state.page.text and "[:]" not in state.page.text
    context = decider.contexts[0]
    assert context.field["label"] == "Name"
    assert "<" not in context.page["text"] and f"[{ids['name']}] Name" in context.page["text"]
    # variable values are masked in the names too
    assert "] {{who}}" in state.page.text and "Subscribe" not in state.model_dump_json()


@pytest.mark.asyncio
async def test_accessible_page_text_names_each_field_once(session: NotteSession) -> None:
    form = """<html><body><form>
<label for="name">Full name</label> <input id="name" name="name"><br>
<label for="plan">Plan</label>
<select id="plan" name="plan"><option value="free">Free</option><option value="pro">Pro</option></select><br>
<input type="checkbox" id="terms" name="terms"><label for="terms">I accept the terms</label><br>
<input type="checkbox" id="news" name="news"><label for="news">Send me the newsletter</label><br>
<button type="submit">Sign up</button></form></body></html>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(form)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("sign up", decider=decider)
    assert decider.states[0].page.text.splitlines() == [
        f"[{ids['name']}] Full name",
        f"[{ids['plan']}] Plan",
        f"[{ids['terms']}] I accept the terms",
        f"[{ids['news']}] Send me the newsletter",
        "[B3] Sign up",
    ]


@pytest.mark.asyncio
async def test_html_labels_show_the_whole_select(session: NotteSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_ACT_LABELS", "html")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("look", decider=decider)
    country = next(e for e in decider.states[0].elements if e["index"] == ids["country"])
    # a <select> renders over several lines: its label keeps all of them
    assert country["label"].startswith('<select name="country">') and country["label"].endswith("</select>")


@pytest.mark.asyncio
async def test_a_hidden_checkbox_label_before_a_field_stays_clickable(session: NotteSession) -> None:
    page = """<html><body><form>
<label style="cursor:pointer" onclick="document.getElementById('remember').click()">Remember me</label>
<input type="checkbox" id="remember" hidden>
<input type="email" name="email" placeholder="Email">
<label for="password" style="cursor:pointer" onclick="">Password</label>
<input type="password" id="password" name="password">
</form></body></html>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("look", decider=decider)
    elements = {e["label"]: e for e in decider.states[0].elements}
    # the checkbox's only visible part is still offered, and does not name the email field
    assert elements["Remember me"]["role"] == "clickable"
    assert "Email" in elements and elements["Email"]["role"] == "textbox"
    # the password label belongs to its field: named once, not offered separately
    assert [e["label"] for e in decider.states[0].elements].count("Password") == 1
    assert elements["Password"]["role"] == "textbox"


@pytest.mark.asyncio
async def test_labels_link_fields_within_their_own_shadow_root(session: NotteSession) -> None:
    # two components reuse the id "email": each label names the field of its own shadow root
    page = """<html><body><div id="a"></div><div id="b"></div><script>
for (const [host, name] of [["a", "Work email"], ["b", "Personal email"]]) {
  const root = document.getElementById(host).attachShadow({mode: "open"});
  root.innerHTML = `<label for="email" style="cursor:pointer" onclick="">${name}</label><input id="email" name="${host}">`;
}
</script></body></html>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("look", decider=decider)
    labels = [e["label"] for e in decider.states[0].elements if e["role"] == "textbox"]
    assert labels == ["Work email", "Personal email"]


@pytest.mark.asyncio
async def test_a_slotted_label_names_the_field_next_to_its_host(session: NotteSession) -> None:
    # the label is slotted into a custom element (light DOM of the host), the field is in the main document
    page = """<html><body><my-label><label for="email" style="cursor:pointer" onclick="">Work email</label></my-label>
<input id="email" name="email"><script>
customElements.define("my-label", class extends HTMLElement {
  constructor() { super(); this.attachShadow({mode: "open"}).innerHTML = "<slot></slot>"; }
});
</script></body></html>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("look", decider=decider)
    assert [e["label"] for e in decider.states[0].elements if e["role"] == "textbox"] == ["Work email"]


@pytest.mark.asyncio
async def test_another_observation_during_the_decision_does_not_switch_the_target(session: NotteSession) -> None:
    page = session.window.page
    await page.set_content(
        "<div id='top'></div><form><button type='button' id='target' "
        "onclick=\"document.getElementById('out').textContent = 'target'\">Continue</button></form><p id='out'></p>"
    )
    obs = await session.aobserve()
    target = next(a.id for a in obs.space.interaction_actions if (a.text_label or "") == "Continue")

    async def renumber_while_deciding() -> None:
        # another call adds a button before the target (in another parent: the target's XPath is unchanged)
        # and observes the session, so the target's id now names the new button
        await page.eval_on_selector(
            "#top",
            "el => el.innerHTML = `<button type='button' onclick=\"document.getElementById('out').textContent = 'other'\">Delete</button>`",
        )
        renumbered = await session.aobserve()
        assert next(a for a in renumbered.space.interaction_actions if a.id == target).text_label == "Delete"

    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": target}], on_choose=renumber_while_deciding)
    result = await session.aact("continue", decider=decider)
    assert result.status == "executed"
    assert await page.inner_text("#out") == "target"


@pytest.mark.asyncio
async def test_fields_get_their_real_names(session: NotteSession) -> None:
    # names the old adjacency approximation got wrong: a `<label for>` away from its field, `aria-labelledby`
    page = """<html><body><form>
<label for="phone">Phone number</label><p>We only call about your order.</p><input id="phone" name="tel">
<span id="when">Delivery date</span><input aria-labelledby="when" name="d1">
</form></body></html>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("look", decider=decider)
    labels = [e["label"] for e in decider.states[0].elements if e["role"] == "textbox"]
    assert labels == ["Phone number", "Delivery date"]


@pytest.mark.asyncio
async def test_a_renamed_field_is_stale(session: NotteSession) -> None:
    # the field's own text, value and selectors stay; only the `<label for>` naming it changes
    page = session.window.page
    await page.set_content('<label for="q">Search</label><p>hint</p><input id="q" name="q">')
    ids = await _ids(session)
    target = ids["q"]

    names = iter(["Delete account", "Close account"])

    async def rename() -> None:
        await page.eval_on_selector("label", "(el, name) => el.textContent = name", next(names))

    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": target}] * 2, on_choose=rename)
    result = await session.aact("click the search box", decider=decider, raise_on_failure=False)
    # renamed while each decision was taken: decided again once, then stale, never executed on an old name
    assert len(decider.states) == 2 and result.status == "stale" and result.execution is None


@pytest.mark.asyncio
async def test_enter_is_stale_when_the_focus_moved(session: NotteSession) -> None:
    page = session.window.page
    await page.set_content("<input id='search'><form><input id='other'></form>")
    await page.focus("#search")

    fields = iter(["#other", "#search"])

    async def move_focus() -> None:
        await page.focus(next(fields))

    decider = FakeDecider(choices=[{"operation": "PRESS_ENTER"}] * 2, on_choose=move_focus)
    result = await session.aact("submit the search", decider=decider, raise_on_failure=False)
    # Enter would go to another field than the decision saw: decided again, then stale
    assert result.status == "stale" and len(decider.states) == 2
    # a focus that stays put lets Enter through
    still = await session.aact("submit", decider=FakeDecider(choices=[{"operation": "PRESS_ENTER"}]))
    assert still.status == "executed"


@pytest.mark.asyncio
async def test_enter_is_fresh_while_the_page_adds_elements_before_the_focus(session: NotteSession) -> None:
    page = session.window.page
    # an ad or a lazy widget inserted above the focused field, again and again
    await page.set_content(
        """<form><input id='search' name='q'></form>
<script>setInterval(() => document.body.prepend(document.createElement('div')), 50)</script>"""
    )
    await page.focus("#search")

    async def slow_decision() -> None:
        await asyncio.sleep(0.3)

    decider = FakeDecider(choices=[{"operation": "PRESS_ENTER"}], on_choose=slow_decision)
    result = await session.aact("submit the search", decider=decider, raise_on_failure=False)
    # the focus stayed on the field: Enter goes where the decision saw it
    assert result.status == "executed" and len(decider.states) == 1


@pytest.mark.asyncio
async def test_a_failed_action_is_recorded_as_failed(session: NotteSession) -> None:
    # a date input rejects a value that is not YYYY-MM-DD: the fill fails
    _ = await session.window.page.goto(f"data:text/html,{quote('<label for=d>Date</label><input id=d type=date>')}")
    ids = await _ids(session)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["d"]}, {"operation": "DONE"}],
        texts=["15/11/2026 secret-looking text"],
    )
    failed = await session.aact("Pick 15 November 2026", decider=decider, raise_on_failure=False)
    assert failed.execution is not None and not failed.execution.success
    _ = await session.aact("Pick 15 November 2026", decider=decider, raise_on_failure=False)
    [entry] = decider.states[-1].recent_actions
    # the error class, never the message (it can quote the page or the value)
    assert entry["error"] and entry["error"].isidentifier()
    assert "Malformed" not in json.dumps(entry)


@pytest.mark.asyncio
async def test_a_raised_failure_is_recorded_too(session: NotteSession) -> None:
    _ = await session.window.page.goto(f"data:text/html,{quote('<label for=d>Date</label><input id=d type=date>')}")
    ids = await _ids(session)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["d"]}, {"operation": "DONE"}], texts=["15/11/2026"]
    )
    with pytest.raises(Exception):  # noqa: B017 (whatever the session raises for a failed fill)
        _ = await session.aact("Pick 15 November 2026", decider=decider)
    _ = await session.aact("Pick 15 November 2026", decider=decider, raise_on_failure=False)
    assert "error" in decider.states[-1].recent_actions[0]


WAIT_PAGE = '<input id="field" disabled aria-label="Name"><p id="status">Loading</p>'
# enables the field 1.5 s after it runs
ENABLE_LATER = """setTimeout(() => { document.getElementById('field').disabled = false;
document.getElementById('status').textContent = 'Ready'; }, 1500)"""


async def _wait(session: NotteSession, arm: str | None = None) -> tuple[str, float]:
    """One WAIT decision. `arm` (a page script) runs when the WAIT is decided: a timer it starts is counted from
    the decision, not from the page load, however long observing and deciding take."""

    async def on_choose() -> None:
        if arm is not None:
            _ = await session.window.page.evaluate(arm)

    decider = FakeDecider(choices=[{"operation": "WAIT"}], on_choose=on_choose)
    loop = asyncio.get_running_loop()
    started = loop.time()
    result = await session.aact("Type a name once the field is ready", decider=decider)
    assert result.status == "executed" and result.execution is not None and result.execution.success
    return result.execution.message, loop.time() - started


@pytest.mark.asyncio
async def test_wait_ends_when_the_page_changes(session: NotteSession) -> None:
    # the page enables its field 1.5 s after the WAIT is decided: past the old fixed 1 s, within the bound
    _ = await session.window.page.goto(f"data:text/html,{quote(WAIT_PAGE)}")
    message, elapsed = await _wait(session, arm=ENABLE_LATER)
    assert message.startswith("The page changed") and elapsed < 2.8
    assert await session.window.page.is_enabled("#field")


@pytest.mark.asyncio
async def test_wait_is_bounded_on_a_page_that_does_not_change(session: NotteSession) -> None:
    message, elapsed = await _wait(session)
    assert message == "The page did not change in 3000 ms." and 2.9 < elapsed < 4.5
    # recorded with the session's other actions
    waits = [r for r in session.trajectory.execution_results() if isinstance(r.action, WaitAction)]
    assert [r.message for r in waits] == [message]


@pytest.mark.asyncio
async def test_a_wait_that_ends_on_a_navigation_stays_within_its_bound(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the next page loads, but keeps polling: its network is never idle. The wait still ends within its 3 s
    poll = "<p>Next page</p><script>setInterval(() => fetch('http://slow.test/poll'), 100)</script>"

    async def next_page(route: Any) -> None:
        await route.fulfill(body=poll, content_type="text/html")

    async def answer_later(route: Any) -> None:
        await asyncio.sleep(0.3)
        await route.fulfill(body="ok")

    await session.window.page.route("http://slow.test/", next_page)
    await session.window.page.route("http://slow.test/poll", answer_later)

    async def network_idle() -> None:
        # what the session's own settle (network idle, up to 10 s) takes on such a page
        await asyncio.sleep(10)

    monkeypatch.setattr(session.window, "long_wait", network_idle)
    _ = await session.window.page.goto(f"data:text/html,{quote('<p>Redirecting</p>')}")
    message, elapsed = await _wait(session, arm="setTimeout(() => location.href = 'http://slow.test/', 500)")
    assert message.startswith("The page navigated") and elapsed < 4
    assert session.window.page.url == "http://slow.test/"


@pytest.mark.asyncio
async def test_a_wait_whose_script_fails_is_a_failed_wait(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from notte_browser import session as local

    # a page that breaks the script (not a navigation): the wait fails, it is not reported as a change
    monkeypatch.setattr(local, "_WAIT_FOR_CHANGE_JS", "() => { throw new Error('blocked by the page') }")
    decider = FakeDecider(choices=[{"operation": "WAIT"}, {"operation": "WAIT"}, {"operation": "DONE"}])
    result = await session.aact("wait", decider=decider, raise_on_failure=False)
    assert result.execution is not None and not result.execution.success
    assert "blocked by the page" in result.execution.message
    with pytest.raises(ActionExecutionError):
        _ = await session.aact("wait", decider=decider)
    _ = await session.aact("wait", decider=decider, raise_on_failure=False)
    assert [entry.get("error") for entry in decider.states[-1].recent_actions] == ["ActionExecutionError"] * 2


@pytest.mark.asyncio
async def test_wait_ends_on_a_navigation(session: NotteSession) -> None:
    _ = await session.window.page.goto(f"data:text/html,{quote('<p>Redirecting</p>')}")
    # the page navigates 500 ms after the WAIT is decided: after the freshness check, during the wait
    message, elapsed = await _wait(session, arm="setTimeout(() => location.href = 'about:blank', 500)")
    assert message.startswith("The page navigated") and elapsed < 2.8
    assert session.window.page.url == "about:blank"


@pytest.mark.asyncio
async def test_typed_inputs_show_their_type_and_format(session: NotteSession) -> None:
    form = """<html><body>
<label for="date">Date</label> <input id="date" type="date">
<label for="qty">Tickets</label> <input id="qty" type="number" value="1">
<label for="cv">CV</label> <input id="cv" type="file">
<label for="name">Name</label> <input id="name"></body></html>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(form)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["date"]}], texts=["2026-11-15"])
    result = await session.aact("Pick 15 November 2026", decider=decider)

    elements = {e["index"]: e for e in decider.states[0].elements}
    assert elements[ids["date"]]["type"] == "date" and elements[ids["date"]]["format"] == "YYYY-MM-DD"
    assert elements[ids["qty"]]["type"] == "number" and "format" not in elements[ids["qty"]]
    assert "type" not in elements[ids["name"]] and "format" not in elements[ids["name"]]
    # a file input is shown, with no operation: act() cannot upload a file, and a click opens a chooser
    assert elements[ids["cv"]]["type"] == "file" and elements[ids["cv"]]["operations"] == []
    assert all(
        ids["cv"] not in question.criteria for name, question in decider.questions[0].items() if name != "operation"
    )
    # the decider sees the format in the target, and the writer gets it with the field
    assert decider.questions[0]["type_text_target"].criteria[ids["date"]]["format"] == "YYYY-MM-DD"
    assert decider.contexts[0].field == {
        "index": ids["date"],
        "label": "Date",
        "role": "textbox",
        "value": "",
        "type": "date",
        "format": "YYYY-MM-DD",
    }
    assert result.success and await session.window.page.input_value("#date") == "2026-11-15"


@pytest.mark.asyncio
async def test_a_dialog_says_the_page_is_behind_it(session: NotteSession, monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_core.act.prompts import DIALOG_COVERS_PAGE

    page = """<html><body><nav><a href="#pricing">Pricing</a></nav>
<div style="position:fixed;inset:0;background:#0008"><div role="dialog" aria-modal="true">
<h2>Cookies</h2><button>Accept all</button></div></div></body></html>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    for labels in ("accessible", "html"):
        monkeypatch.setenv("NOTTE_ACT_LABELS", labels)
        decider = FakeDecider(choices=[{"operation": "DONE"}])
        _ = await session.aact("open the Pricing page", decider=decider)
        # only the dialog is observed: the first line says the page is behind it
        assert [e["label"] for e in decider.states[0].elements] == (
            ["Accept all"] if labels == "accessible" else ["<button>Accept all</button>"]
        )
        assert decider.states[0].page.text.splitlines()[0] == DIALOG_COVERS_PAGE

    # without a dialog, no such line
    _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("look", decider=decider)
    assert DIALOG_COVERS_PAGE not in decider.states[0].page.text


@pytest.mark.asyncio
async def test_typing_an_unlisted_option_is_offered_by_the_operation(session: NotteSession) -> None:
    from notte_core.act.prompts import OPERATION_LABELS, TYPE_TEXT_OPTION

    options = "".join(f"<option value='c{i}'>Country {i:03d}</option>" for i in range(120))
    page = f"<label for='c'>Country</label><select id='c'><option value=''>Pick</option>{options}</select>"
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["c"]}, {"operation": "DONE"}],
        texts=["Country 100"],
    )
    result = await session.aact("Pick Country 100", decider=decider)

    element = decider.states[0].elements[0]
    assert element["more_options"] is True and "Country 100" not in {o["label"] for o in element["options"]}
    # the TYPE_TEXT operation says it also picks an option that is not listed
    assert decider.questions[0]["operation"].criteria["TYPE_TEXT"] == TYPE_TEXT_OPTION
    assert result.success and await session.window.page.input_value("#c") == "c100"
    # a page without such a dropdown keeps the plain label
    _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
    _ = await session.aact("look", decider=decider)
    assert decider.questions[1]["operation"].criteria["TYPE_TEXT"] == OPERATION_LABELS["TYPE_TEXT"]


@pytest.mark.asyncio
async def test_page_text_follows_the_viewport(session: NotteSession) -> None:
    def page(count: int) -> str:
        paragraphs = "".join(f"<p>Paragraph {i}: " + "lorem ipsum dolor sit amet " * 8 + "</p>" for i in range(count))
        return f"<h1>Annual review</h1><a href='#top'>Top link</a>{paragraphs}<label>Note <input id='note'></label>"

    _ = await session.window.page.goto(f"data:text/html,{quote(page(30))}")
    decider = FakeDecider(choices=[{"operation": "DONE"}, {"answer": "no"}])
    _ = await session.aact("look", decider=decider)
    # the field further down is not an element yet, and the action is decided on the text in view
    assert [e["label"] for e in decider.states[0].elements] == ["Top link"]
    text = decider.states[0].page.text
    assert "] Top link" in text and "Note" not in text
    assert text.endswith("characters of page text below the viewport not shown: scroll down to read them)")
    # a question about the page reads all of it, and where each part is
    _ = await session.achoose("Is there a note field?", ["yes", "no"], decider=decider)
    text = decider.states[1].page.text
    below = text.index("--- below the viewport: scroll down to reach ---")
    assert text.index("] Top link") < below < text.index("Note")

    # past the page text cap
    _ = await session.window.page.goto(f"data:text/html,{quote(page(80))}")
    _ = await session.window.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["note"]}], texts=["hello"])
    _ = await session.aact("write hello in the note", decider=decider)
    # scrolled to the bottom, the decider and the writer read the bottom of the page, not its top
    for text in (decider.states[0].page.text, decider.contexts[0].page["text"]):
        assert f"[{ids['note']}] Note" in text and "Annual review" not in text
    assert await session.window.page.input_value("#note") == "hello"


@pytest.mark.asyncio
async def test_a_read_only_combobox_is_set_by_its_option_label(session: NotteSession) -> None:
    # the rendered page does not show `readonly`: the element signatures do
    page = """<label for="country">Country</label>
<input id="country" role="combobox" readonly aria-controls="list" aria-expanded="false" onclick="list.hidden=false">
<ul id="list" role="listbox" hidden><li role="option" onclick="country.value='France'">France</li></ul>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["country"]}], texts=["France"])
    result = await session.aact("Choose France", decider=decider, raise_on_failure=False)
    # chosen from the list by its label, not typed into the read-only input
    assert isinstance(result.action, SelectDropdownOptionAction) and result.action.value == "France"


@pytest.mark.asyncio
async def test_an_unlisted_option_is_typed_by_its_label(session: NotteSession) -> None:
    # 60 options: the live state lists the first 50, the others are typed by label; labels are not values
    options = (
        "".join(f'<option value="C{i}">Country {i}</option>' for i in range(59))
        + '<option value="PT">Portugal</option>'
    )
    _ = await session.window.page.goto(
        f"data:text/html,{quote(f'<select id=country><option value=>Choose</option>{options}</select>')}"
    )
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["country"]}], texts=["Portugal"])
    result = await session.aact("Set the country to Portugal", decider=decider)
    assert isinstance(result.action, SelectDropdownOptionAction) and result.action.value == "Portugal"
    assert result.execution is not None and result.execution.success
    # Playwright's select_option matches a string against option values and labels
    assert await session.window.page.input_value("#country") == "PT"


CONSENT_PAGE = """<header><a href="#home">Home</a> <a href="#pricing">Pricing</a></header><h1>Acme</h1>
<div id="backdrop" style="position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center">
<div role="dialog" aria-modal="true" aria-labelledby="t" style="background:#fff;padding:24px">
<h2 id="t">We value your privacy</h2><p>We use cookies.</p>
<button onclick="backdrop.remove()">Accept all</button> <button onclick="backdrop.remove()">Reject all</button>
</div></div>"""


@pytest.mark.asyncio
async def test_a_dialog_over_the_page_is_closed_by_its_own_operation(session: NotteSession) -> None:
    _ = await session.window.page.goto(f"data:text/html,{quote(CONSENT_PAGE)}")
    decider = FakeDecider(choices=[{"operation": "CLOSE_DIALOG", "close_dialog_target": "B2"}, {"operation": "DONE"}])
    result = await session.aact("Open the Pricing page", decider=decider)
    # offered only while the dialog covers the page, executed as a click on the chosen button
    assert "CLOSE_DIALOG" in decider.questions[0]["operation"].criteria
    assert result.status == "executed" and result.operation == "CLOSE_DIALOG" and result.target == "B2"
    assert await session.window.page.locator("#backdrop").count() == 0
    _ = await session.aact("Open the Pricing page", decider=decider)
    assert "CLOSE_DIALOG" not in decider.questions[1]["operation"].criteria
    assert decider.states[1].recent_actions[0]["kind"] == "CLOSE_DIALOG"
    assert "Pricing" in decider.states[1].page.text


# the next observation sees what an action started (`notte_core.act.settle`)
COMBOBOX = """<label for="to">Where to?</label>
<input id="to" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="list">
<ul id="list" role="listbox"></ul>
<script>
const input = document.getElementById('to'), list = document.getElementById('list');
const show = () => { list.innerHTML = '<li role=option>Tokyo, Japan</li><li role=option>Haneda Airport (HND)</li>';
  input.setAttribute('aria-expanded', 'true'); };
input.addEventListener('input', () => LOAD);
</script>"""
# suggestions from a request, or after a debounce with nothing in flight
SUGGEST = {
    "fetch": "fetch('/suggest?q=' + input.value).then(show)",
    "timer": "setTimeout(show, 600)",
}

SPA = """<h1>Code</h1><a id="issues" href="/issues">Issues</a><button>Go to file</button>
<script>
const render = () => { document.body.innerHTML = '<h1>Issues</h1><button>Labels</button>'; };
document.getElementById('issues').addEventListener('click', (e) => { e.preventDefault(); NAVIGATE; });
</script>"""
NAVIGATE = {
    # fetch the next page, then pushState and render it
    "fetch": "fetch('/issues.json').then(() => { history.pushState({}, '', '/issues'); render(); })",
    # pushState first, render later
    "timer": "setTimeout(() => history.pushState({}, '', '/issues'), 300); setTimeout(render, 1500)",
}


async def _serve(session: NotteSession, html: str, delay: float = 0.6) -> None:
    """`html` at http://app.test/; every other path answers after `delay` seconds."""

    async def app(route: Any) -> None:
        if route.request.url == "http://app.test/":
            await route.fulfill(body=html, content_type="text/html")
            return
        await asyncio.sleep(delay)
        await route.fulfill(body="{}", content_type="application/json")

    await session.window.page.route("http://app.test/**", app)
    _ = await session.window.page.goto("http://app.test/")


async def _next_state(session: NotteSession, decider: FakeDecider, instruction: str) -> DecisionState:
    result = await session.aact(instruction, decider=decider)
    assert result.status == "executed" and result.success
    _ = await session.aact(instruction, decider=decider)
    return decider.states[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("load", list(SUGGEST))
async def test_typing_waits_for_the_suggestions(session: NotteSession, load: str) -> None:
    await _serve(session, COMBOBOX.replace("LOAD", SUGGEST[load]))
    ids = await _ids(session)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["to"]}, {"operation": "DONE"}], texts=["Tokyo"]
    )
    state = await _next_state(session, decider, "Fly to Tokyo")
    labels = [e["label"] for e in state.elements]
    assert "Tokyo, Japan" in labels and "Haneda Airport (HND)" in labels


@pytest.mark.asyncio
@pytest.mark.parametrize("navigate", list(NAVIGATE))
async def test_a_client_side_navigation_is_observed_once_rendered(session: NotteSession, navigate: str) -> None:
    await _serve(session, SPA.replace("NAVIGATE", NAVIGATE[navigate]))
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": ids["issues"]}, {"operation": "DONE"}])
    state = await _next_state(session, decider, "Open the issues")
    assert state.page.url == "http://app.test/issues"
    assert [e["label"] for e in state.elements] == ["Labels"]


@pytest.mark.asyncio
async def test_typing_in_a_plain_field_costs_little(session: NotteSession) -> None:
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}], texts=["Jane"])
    result = await session.aact("Sign up as Jane", decider=decider)
    assert result.success and result.timings.execute_ms < 800


@pytest.mark.asyncio
async def test_the_settle_is_bounded_on_a_page_that_keeps_loading(session: NotteSession) -> None:
    # every click starts a request that never answers within the bound
    page = "<button onclick=\"fetch('/slow')\">Load</button>"
    await _serve(session, page, delay=10)
    decider = FakeDecider(choices=[{"operation": "CLICK"}])
    result = await session.aact("Load", decider=decider)
    assert result.success and result.timings.execute_ms < 3_800


@pytest.mark.asyncio
async def test_a_listbox_or_slider_is_not_a_text_field(session: NotteSession) -> None:
    # a combobox's suggestion list (some options scrolled out of its view) and a pane splitter get I ids
    page = """<label for="to">Where to?</label><input id="to" role="combobox" aria-expanded="true" aria-controls="s">
<ul id="s" role="listbox" aria-label="Search suggestions"><li role="option">Tokyo, Japan</li></ul>
<ul id="n" role="listbox" style="height:40px;overflow:auto" tabindex="0">
<li role="option" style="height:30px">1</li><li role="option" style="height:30px;visibility:hidden">2</li></ul>
<div id="split" role="slider" aria-label="Draggable pane splitter" tabindex="0" aria-valuenow="50"
style="width:10px;height:60px;background:#888"></div>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("Go to Tokyo", decider=decider)
    elements = {e["index"]: e for e in decider.states[0].elements}
    # no TYPE_TEXT (a fill fails on them), and a listbox offers no CLICK either: it would land on an option
    assert elements[ids["s"]] == {"index": ids["s"], "label": "Search suggestions", "role": "listbox", "operations": []}
    assert elements[ids["n"]]["role"] == "listbox" and elements[ids["n"]]["operations"] == []
    assert elements[ids["split"]]["role"] == "slider" and elements[ids["split"]]["operations"] == ["CLICK"]
    # an unnamed listbox is not named after the text of the options it hides
    assert elements[ids["n"]]["label"] == "listbox"
    assert not {ids["s"], ids["n"], ids["split"]} & set(decider.questions[0]["type_text_target"].criteria)
    assert "Tokyo, Japan" in [e["label"] for e in elements.values() if e["role"] == "option"]


@pytest.mark.asyncio
async def test_a_search_box_without_suggestions_shows_no_list(session: NotteSession) -> None:
    # a quick-search dialog after typing a query: the suggestion list is on screen (its padding) with no option
    page = """<div role="dialog" aria-modal="true" aria-label="Quick search"><h2>Quick search</h2>
<input id="q" role="combobox" aria-expanded="false" aria-controls="s" aria-label="Search or jump to" value="flask">
<ul id="s" role="listbox" aria-label="Search suggestions" style="padding:4px"></ul><a href="/tips">Search syntax tips</a></div>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("Search for flask", decider=decider)
    state = decider.states[0]
    assert [e["role"] for e in state.elements] == ["combobox", "link"]
    assert "Search suggestions" not in state.page.text and "Search syntax tips" in state.page.text


@pytest.mark.asyncio
async def test_unnamed_fields_are_named_by_context_not_content(session: NotteSession) -> None:
    # a date picker's month and year selects, and a text field with no label tied to it
    years = "".join(f"<option{' selected' if y == 2026 else ''}>{y}</option>" for y in range(1900, 2101))
    months = "".join(f"<option>{m}</option>" for m in ("January", "February", "March", "October", "December"))
    page = f"""<p>Date of Birth</p><input id="birth" value="23 Oct 2026">
<select id="month">{months}</select><select id="year">{years}</select>
<p>Notes</p><textarea id="notes">already typed</textarea>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("Set the birth date", decider=decider)
    labels = {e["index"]: e["label"] for e in decider.states[0].elements}
    assert labels[ids["birth"]] == "Date of Birth" and labels[ids["notes"]] == "Notes"
    assert labels[ids["month"]] == "January … December" and labels[ids["year"]] == "1900 … 2100"
    text = decider.states[0].page.text
    assert f"[{ids['year']}] 1900 … 2100" in text and "1901" not in text and "23 Oct 2026" not in text


@pytest.mark.asyncio
async def test_a_file_input_offers_nothing_and_blocked_says_why(session: NotteSession) -> None:
    from notte_core.act.prompts import BLOCKED, BLOCKED_FILE_UPLOAD

    page = """<form><input id="file" type="file" name="file"><input type="submit" value="Upload"></form>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "BLOCKED"}])
    result = await session.aact("Upload report.pdf", decider=decider, raise_on_failure=False)
    element = next(e for e in decider.states[0].elements if e["index"] == ids["file"])
    assert element["type"] == "file" and element["operations"] == []
    assert ids["file"] not in decider.questions[0]["click_target"].criteria
    # the decider is told, and so is the caller
    assert decider.questions[0]["operation"].criteria["BLOCKED"] == BLOCKED_FILE_UPLOAD
    assert result.status == "blocked" and "file upload is not supported by act()" in (result.message or "")
    # on other pages, BLOCKED is unchanged
    _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("look", decider=decider)
    assert decider.questions[0]["operation"].criteria["BLOCKED"] == BLOCKED


@pytest.mark.asyncio
async def test_only_the_dialog_is_offered_while_it_covers_the_page(session: NotteSession) -> None:
    # the page behind the dialog is aria-hidden, not covered: still hit-testable, so observed
    page = """<main aria-hidden="true"><a href="#f">Flights</a><button aria-label="Main menu"></button></main>
<div role="dialog" aria-modal="true" style="position:fixed;top:40px;left:40px">
<input aria-label="Where else?" role="combobox"></div>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("Fly from Paris", decider=decider)
    assert [e["label"] for e in decider.states[0].elements] == ["Where else?"]
    assert all("Flights" not in str(question.criteria) for question in decider.questions[0].values())


@pytest.mark.asyncio
async def test_a_field_with_no_value_is_skipped_not_blocked(session: NotteSession) -> None:
    page = """<form><p>Travel dates</p><input id="dep" aria-label="Departure" placeholder="Leave on">
<label for="from">From</label><input id="from" value="Paris">
<label for="notes">Notes</label><textarea id="notes"></textarea><button type="button">Search</button></form>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    search = next(n.id for n in session.snapshot.interaction_nodes() if n.inner_text() == "Search")
    decider = FakeDecider(
        choices=[
            {"operation": "TYPE_TEXT", "type_text_target": ids["dep"]},
            {"operation": "CLICK", "click_target": search},
        ],
        texts=[None],
    )
    result = await session.aact("Search flights from Paris", decider=decider)
    # the writer is told what is around the field and what the other fields hold
    context = decider.contexts[0]
    assert context.field == {
        "index": ids["dep"],
        "label": "Departure",
        "role": "textbox",
        "value": "",
        "placeholder": "Leave on",
        "nearby": "Travel dates",
    }
    assert context.page["fields"] == [{"index": ids["from"], "label": "From", "value": "Paris"}]
    # no value: decided again without that field, which the history explains
    assert result.status == "executed" and result.target == search
    assert ids["dep"] not in decider.questions[1]["type_text_target"].criteria
    assert decider.states[1].recent_actions[-1] == {
        "action": "Departure",
        "kind": "TYPE_TEXT",
        "text": None,
        "page_changed": False,
        "error": "NoValueFromInstruction",
    }

    # "" in an empty field is no value either; twice in one call blocks
    decider = FakeDecider(
        choices=[
            {"operation": "TYPE_TEXT", "type_text_target": ids["notes"]},
            {"operation": "TYPE_TEXT", "type_text_target": ids["dep"]},
        ],
        texts=["", None],
    )
    blocked = await session.aact("Search flights", decider=decider, raise_on_failure=False)
    assert blocked.status == "blocked" and "Departure" in (blocked.message or "")
    assert await session.window.page.input_value("#notes") == ""


@pytest.mark.asyncio
async def test_a_filled_password_can_be_cleared(session: NotteSession) -> None:
    page = '<label for="pw">Password</label><input id="pw" type="password" value="hunter2">'
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["pw"]}], texts=[""])
    result = await session.aact("Clear the password", decider=decider)
    # a password shows only that it is filled, not its value: "" still clears it
    assert result.status == "executed" and await session.window.page.input_value("#pw") == ""


@pytest.mark.asyncio
async def test_reset_forgets_the_previous_actions(session: NotteSession) -> None:
    ids = await _ids(session)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}, {"operation": "DONE"}], texts=["Jane"]
    )
    _ = await session.aact("Type Jane", decider=decider)
    await session.areset()
    _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
    _ = await session.aact("Type Jane", decider=decider)
    assert decider.states[-1].recent_actions == []


@pytest.mark.asyncio
async def test_a_reset_keeping_the_browser_keeps_masking_private_values() -> None:
    private = "jane.private@example.test"
    session = NotteSession(headless=True, keep_alive=True)
    await session.astart()
    try:
        _ = await session.window.page.goto(f"data:text/html,{quote(PAGE)}")
        ids = await _ids(session)
        decider = FakeDecider(
            choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}, {"answer": "a"}],
            texts=["{{email}}"],
        )
        _ = await session.aact("Type the email", variables={"email": private}, decider=decider)
        # the browser stays open with the value in the field
        await session.areset()
        assert await session.window.page.input_value("#name") == private
        _ = await session.achoose("Which?", ["a", "b"], decider=decider)
        assert private not in decider.states[-1].model_dump_json()
        assert decider.states[-1].recent_actions == []
    finally:
        session._keep_alive = False  # pyright: ignore[reportPrivateUsage]
        await session.astop()


@pytest.mark.asyncio
async def test_an_invalid_page_answer_is_asked_again_once(session: NotteSession) -> None:
    class BrokenOnce(FakeDecider):
        async def choose(self, state, questions):  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
            answers = await super().choose(state, questions)  # pyright: ignore[reportUnknownArgumentType]
            if len(self.states) == 1:
                answers.answers["answer"].probabilities["missing"] = 0.0
            return answers

    decider = BrokenOnce(choices=[{"answer": "Signup"}] * 2)
    choice = await session.achoose("Which page is this?", ["Signup", "Login"], decider=decider)
    assert choice.choice == "Signup" and len(decider.states) == 2
    decider = BrokenOnce(choices=[{"answer": "YES"}] * 2)
    assert await session.acheck("Is it a form?", decider=decider) == pytest.approx(0.9)


# an issue search applied by its button, a live filter, and a filter that puts its query in the URL as it is typed
ISSUES = """<h1>Issues</h1>
<label for="q">Search issues</label><input id="q" value="is:open">
<button id="search" onclick="document.getElementById('shown').textContent = document.getElementById('q').value">Search</button>
<p>Showing: <span id="shown">is:open</span></p>
<label for="filter">Filter labels</label>
<input id="filter" oninput="for (const li of document.querySelectorAll('#labels li'))
  li.hidden = !li.textContent.includes(this.value)">
<ul id="labels"><li>bug</li><li>docs</li><li>feature</li></ul>
<label for="live">Find a milestone</label>
<input id="live" oninput="history.replaceState(null, '', '?milestone=' + encodeURIComponent(this.value))">"""


async def _type(session: NotteSession, decider: FakeDecider, field: str, text: str) -> DecisionState:
    """Type `text` in the field `field` (its id attribute) and return the state of the next decision."""
    ids = await _ids(session)
    decider.choices += [{"operation": "TYPE_TEXT", "type_text_target": ids[field]}, {"operation": "DONE"}]
    decider.texts.append(text)
    return await _next_state(session, decider, "Show the open bugs")


def _unsubmitted(state: DecisionState) -> list[str]:
    return [e["label"] for e in state.elements if e.get("submitted") is False]


@pytest.mark.asyncio
async def test_typed_text_not_submitted_yet_is_shown_until_submitted(session: NotteSession) -> None:
    await _serve(session, ISSUES)
    decider = FakeDecider(choices=[])
    state = await _type(session, decider, "q", "is:open label:bug")
    # the field, the history and DONE say the query is typed, not applied
    assert _unsubmitted(state) == ["Search issues"]
    assert state.recent_actions[-1]["kind"] == "TYPE_TEXT" and state.recent_actions[-1]["submitted"] is False
    done = decider.questions[-1]["operation"].criteria["DONE"]
    assert "'Search issues' is not submitted" in done and "only asks to type it" in done

    # clicking a checkbox or another field submits nothing; the Search button does
    ids = await _ids(session)
    decider.choices += [{"operation": "CLICK", "click_target": ids["filter"]}, {"operation": "DONE"}]
    state = await _next_state(session, decider, "Show the open bugs")
    assert _unsubmitted(state) == ["Search issues"]
    decider.choices += [{"operation": "CLICK", "click_target": ids["search"]}, {"operation": "DONE"}]
    state = await _next_state(session, decider, "Show the open bugs")
    assert _unsubmitted(state) == [] and all("submitted" not in a for a in state.recent_actions)
    assert decider.questions[-1]["operation"].criteria["DONE"] == prompts.DONE

    # typed again: Enter submits it
    state = await _type(session, decider, "q", "is:open label:docs")
    assert _unsubmitted(state) == ["Search issues"]
    decider.choices += [{"operation": "PRESS_ENTER"}, {"operation": "DONE"}]
    state = await _next_state(session, decider, "Show the open bugs")
    assert _unsubmitted(state) == []


@pytest.mark.asyncio
async def test_a_field_that_applies_what_is_typed_is_not_unsubmitted(session: NotteSession) -> None:
    await _serve(session, ISSUES)
    decider = FakeDecider(choices=[])
    # a live filter hides the labels that do not match, a live search puts the query in the URL
    state = await _type(session, decider, "filter", "bug")
    assert "docs" not in state.page.text and _unsubmitted(state) == []
    state = await _type(session, decider, "live", "v2")
    assert state.page.url.endswith("?milestone=v2") and _unsubmitted(state) == []
    # a field that applies nothing on its own is
    state = await _type(session, decider, "q", "label:bug")
    assert _unsubmitted(state) == ["Search issues"]
    # the field no longer holds the text: tracking ends
    await session.window.page.fill("#q", "")
    decider.choices.append({"operation": "DONE"})
    _ = await session.aact("Show the open bugs", decider=decider)
    assert _unsubmitted(decider.states[-1]) == []


@pytest.mark.asyncio
async def test_a_goal_that_only_types_still_ends_done(session: NotteSession) -> None:
    ids = await _ids(session)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["name"]}, {"operation": "DONE"}], texts=["Jane"]
    )
    _ = await session.aact("Type Jane in the name field", decider=decider)
    done = await session.aact("Type Jane in the name field", decider=decider)
    # the field is marked, and DONE is still DONE: nothing is submitted on the decider's behalf
    assert _unsubmitted(decider.states[-1]) == ["Name"]
    assert done.status == "done" and done.success and done.action is None
    assert await session.window.page.input_value("#name") == "Jane"
    assert await session.window.page.text_content("#out") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["frame", "shadow"])
async def test_wait_ends_on_a_change_inside_a_frame_or_shadow_root(session: NotteSession, where: str) -> None:
    pages = {
        "frame": '<iframe id="f" srcdoc="<p id=s>Loading</p>"></iframe>',
        "shadow": "<div id=host></div><script>host.attachShadow({mode:'open'}).innerHTML='<p id=s>Loading</p>'</script>",
    }
    arm = {
        "frame": "setTimeout(() => document.getElementById('f').contentDocument.getElementById('s').textContent = 'Ready', 800)",
        "shadow": "setTimeout(() => document.getElementById('host').shadowRoot.getElementById('s').textContent = 'Ready', 800)",
    }
    _ = await session.window.page.goto(f"data:text/html,{quote(pages[where])}")
    await session.window.page.wait_for_timeout(200)
    message, elapsed = await _wait(session, arm=arm[where])
    assert message.startswith("The page changed") and elapsed < 2.8


@pytest.mark.asyncio
async def test_typing_in_a_frame_waits_for_its_suggestions(session: NotteSession) -> None:
    # the autocomplete field and its timer-loaded list are inside a same-origin frame
    inner = COMBOBOX.replace("LOAD", SUGGEST["timer"])
    page = (
        f"<p>Book a flight</p><iframe id='f' width=600 height=400 srcdoc=\"{html.escape(inner, quote=True)}\"></iframe>"
    )
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    await session.window.page.wait_for_timeout(300)
    _ = await session.aobserve()
    field = next(node.id for node in session.snapshot.interaction_nodes() if node.get_role_str() == "combobox")
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": field}, {"operation": "DONE"}], texts=["Tokyo"]
    )
    state = await _next_state(session, decider, "Fly to Tokyo")
    labels = [e["label"] for e in state.elements]
    assert "Tokyo, Japan" in labels and "Haneda Airport (HND)" in labels


@pytest.mark.asyncio
async def test_a_failed_submit_keeps_the_text_unsubmitted(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _serve(session, ISSUES)
    decider = FakeDecider(choices=[])
    _ = await _type(session, decider, "q", "is:open label:bug")
    ids = await _ids(session)
    real_execute = session.aexecute

    async def failing_submit(action: Any, **kwargs: Any) -> Any:
        if getattr(action, "id", None) == ids["search"]:
            raise RuntimeError("the click did not go through")
        return await real_execute(action, **kwargs)

    monkeypatch.setattr(session, "aexecute", failing_submit)
    decider.choices += [{"operation": "CLICK", "click_target": ids["search"]}, {"operation": "DONE"}]
    with pytest.raises(RuntimeError):
        _ = await session.aact("Show the open bugs", decider=decider)
    _ = await session.aact("Show the open bugs", decider=decider)
    # nothing was submitted: the field still holds unsubmitted text
    assert _unsubmitted(decider.states[-1]) == ["Search issues"]


SHOP = """<main>
<h1>Desk lamp</h1><p>3,99€</p>
<section><h2>Complete with</h2>
  <div><div><a href="#bulb"><h3>LED bulb</h3></a><p>4,99€</p></div><button id="bulb-add">Add to cart</button></div>
  <div><div><h3>Lamp shade</h3><p>9,99€</p></div><button id="shade-add">Add to cart</button></div>
</section>
<section><h2>How to get it</h2><button id="lamp-add">Add to cart</button><a id="stores" href="#s">Stores</a></section>
</main>"""
COOKIES = """<div role="dialog" aria-label="Cookies"><h2>Your privacy</h2><button id="accept">Accept</button></div>"""


@pytest.mark.asyncio
async def test_same_named_elements_carry_their_context(session: NotteSession) -> None:
    _ = await session.window.page.goto(f"data:text/html,{quote(SHOP)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("Add the lamp to the cart", decider=decider)
    elements = {e["index"]: e for e in decider.states[0].elements}
    # each "Add to cart" says which section and item it belongs to
    assert elements[ids["bulb-add"]]["context"] == "Complete with › LED bulb"
    assert elements[ids["shade-add"]]["context"] == "Complete with › Lamp shade"
    assert elements[ids["lamp-add"]]["context"] == "Desk lamp › How to get it"
    # in the target criteria and the page text too
    criteria = decider.questions[0]["click_target"].criteria
    assert criteria[ids["bulb-add"]]["element"] == f"[{ids['bulb-add']}] Add to cart (in: Complete with › LED bulb)"
    assert f"[{ids['lamp-add']}] Add to cart (in: Desk lamp › How to get it)" in decider.states[0].page.text
    # a unique name needs no context
    assert "context" not in elements[ids["stores"]]
    assert f"[{ids['stores']}] Stores\n" in decider.states[0].page.text + "\n"


@pytest.mark.asyncio
async def test_a_dialog_does_not_take_the_titles_of_the_page_behind_it(session: NotteSession) -> None:
    from notte_core.act.context import element_contexts

    _ = await session.window.page.goto(f"data:text/html,{quote(SHOP + COOKIES)}")
    ids = await _ids(session)
    contexts = element_contexts(session.snapshot.dom_node)
    assert contexts[ids["accept"]] == "Cookies › Your privacy"
    # the title block before a card's button is the card's, not the next card's
    assert contexts[ids["shade-add"]] == "Complete with › Lamp shade"


@pytest.mark.asyncio
async def test_the_writer_reads_the_context_of_a_same_named_field(session: NotteSession) -> None:
    page = """<form><h2>Billing address</h2><label>Name <input id="billing"></label>
<h2>Shipping address</h2><label>Name <input id="shipping"></label></form>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["shipping"]}], texts=["Jane"])
    _ = await session.aact("Ship to Jane", decider=decider)
    assert decider.contexts[0].field["context"] == "Shipping address"
    assert await session.window.page.input_value("#shipping") == "Jane"


@pytest.mark.asyncio
async def test_the_history_says_which_same_named_element_ran(session: NotteSession) -> None:
    _ = await session.window.page.goto(f"data:text/html,{quote(SHOP)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": ids["bulb-add"]}, {"operation": "DONE"}])
    _ = await session.aact("Add the lamp to the cart", decider=decider)
    _ = await session.aact("Add the lamp to the cart", decider=decider)
    assert decider.states[1].recent_actions[-1]["action"] == "Add to cart (in: Complete with › LED bulb)"


@pytest.mark.asyncio
async def test_the_writer_sees_the_controls_after_a_free_text_field(session: NotteSession) -> None:
    page = """<input id="q" aria-label="Search in your own words" placeholder="Family flats in Paris with a pool">
<button id="dates">Select dates</button><button id="guests">2 adults, 1 room</button><button>Search</button>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "TYPE_TEXT", "type_text_target": ids["q"]}], texts=["Lisbon"])
    _ = await session.aact("Hotels in Lisbon for 2 adults, 13 to 15 November", decider=decider)
    # the dates and guests have their own controls: the writer is told, to type only the destination
    assert decider.contexts[0].page["next_controls"] == ["Select dates", "2 adults, 1 room", "Search"]


@pytest.mark.asyncio
async def test_a_context_shared_by_same_named_elements_is_not_shown(session: NotteSession) -> None:
    page = """<h2>Flight search</h2><input id="dep" aria-label="Departure"><button id="prev"></button>
<button id="next"></button><input id="ret" aria-label="Return"><button id="prev2"></button>"""
    _ = await session.window.page.goto(f"data:text/html,{quote(page)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("Search flights", decider=decider)
    elements = {e["index"]: e for e in decider.states[0].elements}
    # three unnamed buttons of the same section: "(in: Flight search)" tells none of them apart
    assert all("context" not in elements[ids[k]] for k in ("prev", "next", "prev2"))
    assert "(in: " not in decider.states[0].page.text


@pytest.mark.asyncio
@pytest.mark.parametrize("move", ["history.pushState({}, '', '#results')", "location.hash = 'results'"])
async def test_wait_ends_on_a_navigation_within_the_document(session: NotteSession, move: str) -> None:
    # the URL changes 500 ms after the WAIT is decided, with no DOM change (an http page: a data: URL cannot pushState)
    await _serve(session, "<p>Results</p>")
    message, elapsed = await _wait(session, arm=f"setTimeout(() => {{ {move}; }}, 500)")
    assert message.startswith("The page navigated") and elapsed < 2.8
    assert session.window.page.url.endswith("#results")


CARDS = """<div class=card><h3 id=first>Desk lamp</h3><button>Add to cart</button></div>
<div class=card><h3>Bulb</h3><button>Add to cart</button></div>"""


@pytest.mark.asyncio
async def test_a_card_that_changes_while_deciding_is_stale(session: NotteSession) -> None:
    _ = await session.window.page.goto(f"data:text/html,{quote(CARDS)}")
    _ = await session.aobserve()
    first = next(n.id for n in session.snapshot.interaction_nodes() if n.get_role_str() == "button")
    titles = iter(["Floor lamp", "Table lamp"])

    async def retitle() -> None:
        # the card now holds another product; its button, name and selectors stay the same
        await session.window.page.eval_on_selector("#first", "(el, title) => el.textContent = title", next(titles))

    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": first}] * 2, on_choose=retitle)
    result = await session.aact("Add the desk lamp to the cart", decider=decider, raise_on_failure=False)
    assert "(in: Desk lamp)" in decider.states[0].page.text
    assert result.status == "stale" and result.execution is None


@pytest.mark.asyncio
async def test_a_long_private_value_in_a_heading_is_masked_before_it_is_shortened(session: NotteSession) -> None:
    private = "private-" * 10
    # a card's heading echoes the value, longer than a shown title
    cards = (
        f"<div><h3>{private}</h3><button>Add to cart</button></div><div><h3>Bulb</h3><button>Add to cart</button></div>"
    )
    _ = await session.window.page.goto(f"data:text/html,{quote(cards)}")
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await session.aact("Add {{item}} to the cart", variables={"item": private}, decider=decider)
    shown = decider.states[0].model_dump_json()
    assert "(in: {{item}})" in shown and "private-private" not in shown


SITE = {
    "http://site.test/": """<a id="tab" href="/second" target="_blank">Open in a new tab</a>
<button id="later" onclick="setTimeout(() => window.open('/second'), 100)">Open later</button>
<a id="next" href="/next">Next page</a>""",
    "http://site.test/second": "<h1>Second tab</h1><a id='back' href='/'>Home</a>",
    # a search form, and its results page that keeps a request in flight (analytics, polling)
    "http://site.test/search": """<form action="/results"><input id="q" name="q" aria-label="Search"></form>""",
    "http://site.test/results": """<h1>Results</h1><a id="result" href="/second">First result</a>
<script>fetch('/poll')</script>""",
    # rendered once the page's own data arrives, after its load event
    "http://site.test/next": """<h1>Next</h1><script>
window.addEventListener('load', () => fetch('/data').then(() => {
    document.body.insertAdjacentHTML('beforeend', '<button id="rendered">Rendered later</button>');
}));
</script>""",
}


async def _site(session: NotteSession) -> None:
    """`SITE` on the context (new tabs included), each page answered after 200 ms."""

    async def serve(route: Any) -> None:
        url = route.request.url.split("?")[0]
        await asyncio.sleep(5 if url.endswith("/poll") else 0.2)
        await route.fulfill(body=SITE.get(url, "not found"), content_type="text/html")

    await session.window.page.context.route("http://site.test/**", serve)
    _ = await session.window.page.goto("http://site.test/")


@pytest.mark.asyncio
@pytest.mark.parametrize("opener", ["tab", "later"])
async def test_act_continues_in_the_tab_an_action_opened(session: NotteSession, opener: str) -> None:
    await _site(session)
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": ids[opener]}, {"operation": "DONE"}])
    state = await _next_state(session, decider, "Open the second page")
    assert session.window.page.url == "http://site.test/second"
    assert len(session.window.page.context.pages) == 2
    assert state.page.url == "http://site.test/second" and "Second tab" in state.page.text


@pytest.mark.asyncio
async def test_a_navigation_is_observed_once_the_new_page_has_loaded_and_rendered(session: NotteSession) -> None:
    await _site(session)
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": ids["next"]}, {"operation": "DONE"}])
    state = await _next_state(session, decider, "Go to the next page")
    assert state.page.url == "http://site.test/next"
    assert [e["label"] for e in state.elements] == ["Rendered later"]


@pytest.mark.asyncio
async def test_execute_outside_act_still_switches_to_a_new_tab(session: NotteSession) -> None:
    await _site(session)
    ids = await _ids(session)
    result = await session.aexecute(type="click", id=ids["tab"])
    assert result.success and session.window.page.url == "http://site.test/second"


@pytest.mark.asyncio
async def test_a_page_submitted_with_enter_is_observed_once_rendered_not_once_its_requests_end(
    session: NotteSession,
) -> None:
    await _site(session)
    _ = await session.window.page.goto("http://site.test/search")
    await session.window.page.fill("#q", "lamp")
    await session.window.page.focus("#q")
    decider = FakeDecider(choices=[{"operation": "PRESS_ENTER"}, {"operation": "DONE"}])
    result = await session.aact("Search for lamp", decider=decider)
    assert result.success and session.window.page.url == "http://site.test/results?q=lamp"
    # the results page's request takes 5 s: not waited for
    assert result.timings.execute_ms < 2_000
    _ = await session.aact("Search for lamp", decider=decider)
    assert [e["label"] for e in decider.states[-1].elements] == ["First result"]


# a click makes the page inert, then a script renders the dialog it opens (its code loaded on first use)
LATE_DIALOG = """<main id="main"><button id="open" onclick="
document.getElementById('main').inert = true;
setTimeout(() => document.body.insertAdjacentHTML('beforeend',
  '<div role=dialog aria-label=Search><input id=query aria-label=Query><button>Close</button></div>'), 600)
">Search</button><p>Some page text</p></main>"""


@pytest.mark.asyncio
async def test_a_dialog_rendered_after_the_page_went_inert_is_observed(session: NotteSession) -> None:
    _ = await session.window.page.goto(f"data:text/html,{quote(LATE_DIALOG)}")
    ids = await _ids(session)
    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": ids["open"]}, {"operation": "DONE"}])
    state = await _next_state(session, decider, "Search")
    # not the inert page with nothing to act on: the dialog
    assert [e["label"] for e in state.elements] == ["Query", "Close"]


YEARS = "".join(f"<option value='{y}'>{y}</option>" for y in range(1900, 2101))
YEAR_PAGE = f"<p>Date of birth</p><select id='year'>{YEARS}</select>"


class _PrefersSelect(FakeDecider):
    """Picks SELECT whenever it is offered, its first listed option, as Jev did on a cut year list; else TYPE_TEXT."""

    async def choose(self, state: DecisionState, questions: Mapping[str, Question]) -> Answers:
        operation = "SELECT" if "SELECT" in questions["operation"].criteria else "TYPE_TEXT"
        self.choices = [{"operation": operation}, *self.choices[1:]]
        return await super().choose(state, questions)


@pytest.mark.asyncio
async def test_a_value_left_out_of_a_cut_select_is_typed_not_picked_among_the_listed_ones(
    session: NotteSession,
) -> None:
    _ = await session.window.page.goto(f"data:text/html,{quote(YEAR_PAGE)}")
    decider = _PrefersSelect(choices=[{}], texts=["1990"])
    result = await session.aact("Born in 1990", decider=decider)
    assert result.success and await session.window.page.input_value("#year") == "1990"
