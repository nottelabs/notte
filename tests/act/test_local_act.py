"""`NotteSession.act()` / `choose()` / `check()` end to end on a local page, with a scripted decider."""

import asyncio
import json
from collections.abc import AsyncIterator
from urllib.parse import quote

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.act import InvalidDecisionError, NoActionFoundError
from notte_core.actions import CheckAction, FillAction, SelectDropdownOptionAction

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

    with pytest.raises(InvalidDecisionError):
        _ = await session.aact("anything", decider=Broken(choices=[{"operation": "DONE"}]))


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
