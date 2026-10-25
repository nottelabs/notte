"""The model-agnostic part of `act()`: questions built from an observed page, strict answer validation,
mapping answers to notte actions, history and the loop helper. No browser, no model."""

from typing import Any

import pytest
from notte_core.act import ActHistory, ActResult, Answer, Answers, ObservedPage, act_until_done
from notte_core.act.errors import InvalidDecisionError
from notte_core.act.prompts import DIALOG_COVERS_PAGE
from notte_core.act.space import (
    accessible_names,
    accessible_text,
    act_questions,
    build_act_space,
    covered_by_dialog,
    description_lines,
    interpret,
    label_elements,
    label_mode,
    page_state,
    substitute_variables,
    target_action,
    validate_answer,
)
from notte_core.actions import (
    CheckAction,
    ClickAction,
    FillAction,
    InteractionAction,
    ScrollDownAction,
    SelectDropdownOptionAction,
)
from notte_core.element_state import ElementState, SelectOption
from notte_core.snapshot import ViewportData

from tests.act.fakes import answer

DESCRIPTION = """_[:]Sign in
I1[:]<input type="text" name="email"></input>
I2[:]<input type="checkbox" name="remember"></input>
I3[:]<select name="country"></select>
I4[:]<input role="combobox" name="city"></input>
B1[:]<button type="submit">Sign in</button>
L1[:]<a href="/help">Help</a>"""


def _actions() -> list[InteractionAction]:
    return [
        FillAction(id="I1", value="<sample_value>", text_label="email"),
        CheckAction(id="I2", value=True, text_label="remember"),
        SelectDropdownOptionAction(id="I3", value="<sample_value>", text_label="country"),
        SelectDropdownOptionAction(id="I4", value="<sample_value>", text_label="city"),
        ClickAction(id="B1", text_label="Sign in"),
        ClickAction(id="L1", text_label="Help"),
    ]


STATES = {
    "I1": ElementState(value="jane@"),
    "I2": ElementState(checked=False),
    "I3": ElementState(
        value="us",
        options=(
            SelectOption(value="", label="Choose"),
            SelectOption(value="fr", label="France"),
            SelectOption(value="us", label="United States", selected=True),
            SelectOption(value="xx", label="Closed", disabled=True),
        ),
    ),
}


def _page(states: dict[str, ElementState] | None = None, **kwargs: Any) -> ObservedPage:
    fields: dict[str, Any] = dict(
        url="https://example.test/login",
        title="Login",
        description=DESCRIPTION,
        actions=_actions(),
        viewport=ViewportData(
            scroll_x=0, scroll_y=0, viewport_width=1280, viewport_height=720, total_width=1280, total_height=2000
        ),
        states=STATES if states is None else states,
        fingerprint="fp",
    )
    fields.update(kwargs)
    return ObservedPage(**fields)


def test_description_lines_index_rendered_elements_by_id() -> None:
    lines = description_lines(DESCRIPTION)
    assert lines["I1"] == '<input type="text" name="email"></input>'
    assert "_" not in lines and len(lines) == 6


def test_build_act_space_with_live_state() -> None:
    space = build_act_space(_page())
    elements = {e["index"]: e for e in space.elements}

    assert elements["I1"]["value"] == "jane@" and elements["I1"]["operations"] == ["TYPE_TEXT", "CLICK"]
    assert elements["I2"]["checked"] is False and elements["I2"]["role"] == "checkbox"
    # options that are selected or disabled are not SELECT targets
    assert elements["I3"]["value"] == "United States"
    assert elements["I3"]["options"] == [
        {"index": "I3:1", "label": "Choose", "value": ""},
        {"index": "I3:2", "label": "France", "value": "fr"},
    ]
    assert elements["I4"]["role"] == "combobox"
    assert set(space.targets["SELECT"]) == {"I3:1", "I3:2"}
    assert set(space.targets["TYPE_TEXT"]) == {"I1", "I4"}
    assert set(space.targets["CLICK"]) == {"I1", "I2", "I4", "B1", "L1"}
    # scrolled to the top of a long page: no SCROLL_UP
    assert list(space.controls) == ["SCROLL_DOWN", "PRESS_ENTER", "GO_BACK", "WAIT"]
    assert set(space.operations) == {"CLICK", "TYPE_TEXT", "SELECT", *space.controls, "DONE", "BLOCKED"}


def test_build_act_space_without_live_state_types_the_select_option() -> None:
    # without live state, a native select is set by typing its option label
    space = build_act_space(_page(states={}))
    assert "SELECT" not in space.targets
    assert space.targets["TYPE_TEXT"]["I3"].kind == "select_text"
    assert "value" not in next(e for e in space.elements if e["index"] == "I1")


def test_questions_have_one_target_question_per_operation() -> None:
    space = build_act_space(_page())
    questions = act_questions(space, "sign in")
    assert set(questions) == {"operation", "click_target", "type_text_target", "select_target"}
    criteria = questions["select_target"].criteria["I3:2"]
    assert criteria["element"] == '[I3:2] <select name="country"></select> → France'
    assert criteria["current_value"] == "United States"
    assert questions["operation"].instructions["goal"] == "sign in"


def _answers(**choices: str) -> tuple[Answers, Any]:
    space = build_act_space(_page())
    questions = act_questions(space, "sign in")
    answers = {name: answer(choices.get(name, list(q.criteria)[0]), list(q.criteria)) for name, q in questions.items()}
    return Answers(answers=answers, model="fake"), space


@pytest.mark.parametrize(
    ("choices", "expected"),
    [
        ({"operation": "CLICK", "click_target": "B1"}, ClickAction(id="B1")),
        ({"operation": "CLICK", "click_target": "I2"}, CheckAction(id="I2", value=True)),
        ({"operation": "SELECT", "select_target": "I3:2"}, SelectDropdownOptionAction(id="I3", value="fr")),
    ],
)
def test_interpret_maps_answers_to_actions(choices: dict[str, str], expected: InteractionAction) -> None:
    answers, space = _answers(**choices)
    decision = interpret(answers, space)
    assert decision.target is not None
    action = target_action(decision.target, None)
    assert action.type == expected.type and action.id == expected.id
    assert getattr(action, "value", None) == getattr(expected, "value", None)


def test_interpret_fill_and_controls() -> None:
    answers, space = _answers(operation="TYPE_TEXT", type_text_target="I1")
    decision = interpret(answers, space)
    assert decision.target is not None
    fill = target_action(decision.target, "jane@example.com")
    assert isinstance(fill, FillAction) and fill.value == "jane@example.com"

    answers, space = _answers(operation="SCROLL_DOWN")
    decision = interpret(answers, space)
    assert decision.target is None and decision.control is not None
    assert isinstance(decision.control.action, ScrollDownAction)


def test_only_the_chosen_operation_target_is_validated() -> None:
    answers, space = _answers(operation="CLICK", click_target="B1")
    # a malformed answer on an unused head does not matter
    answers.answers["select_target"] = Answer(choice="nope", probabilities={}, confidence=2.0)
    assert interpret(answers, space).target is not None


@pytest.mark.parametrize(
    "bad",
    [
        Answer(choice="C", probabilities={"A": 0.5, "B": 0.5}, confidence=0.5),  # not an option
        Answer(choice="A", probabilities={"A": 1.0}, confidence=0.5),  # options missing
        Answer(choice="A", probabilities={"A": 0.6, "B": 0.6}, confidence=0.5),  # does not sum to 1
        Answer(choice="B", probabilities={"A": 0.7, "B": 0.3}, confidence=0.5),  # not the most probable
        Answer(choice="A", probabilities={"A": 0.7, "B": 0.3}, confidence=float("nan")),
        Answer(choice="A", probabilities={"A": 1.2, "B": -0.2}, confidence=0.5),
    ],
)
def test_validate_answer_is_strict(bad: Answer) -> None:
    with pytest.raises(InvalidDecisionError):
        _ = validate_answer(Answers(answers={"q": bad}, model="m"), "q", {"A": "a", "B": "b"})


def test_validate_answer_missing_question() -> None:
    with pytest.raises(InvalidDecisionError, match="no answer"):
        _ = validate_answer(Answers(answers={}, model="m"), "q", {"A": "a"})


def test_substitute_variables() -> None:
    variables = {"email": "jane@example.com", "name": "Jane"}
    assert substitute_variables("{{ name }} <{{email}}>", variables) == "Jane <jane@example.com>"
    assert substitute_variables("{{unknown}} stays", variables) == "{{unknown}} stays"


def test_signature_changes_with_state_and_label() -> None:
    page = _page()
    assert page.signature("I1") != _page(states={**STATES, "I1": ElementState(value="x")}).signature("I1")
    assert page.signature("B1") == _page(states={}).signature("B1")
    assert page.signature("Z9") is None


def test_history_fills_page_changed_on_next_observation() -> None:
    from notte_core.act.runner import ActHistoryEntry

    history = ActHistory()
    history.entries.append(ActHistoryEntry(action="Sign in", kind="CLICK", text=None, fingerprint="a"))
    history.observed(_page(fingerprint="b"))
    history.entries.append(ActHistoryEntry(action="Help", kind="CLICK", text=None, fingerprint="b"))
    history.observed(_page(fingerprint="b"))
    history.entries.append(ActHistoryEntry(action="x", kind="TYPE_TEXT", text="t", fingerprint="b", pending=False))
    history.observed(_page(fingerprint="c"))
    assert [e["page_changed"] for e in history.recent()] == [True, False, None]
    for i in range(20):
        history.entries.append(ActHistoryEntry(action=str(i), kind="CLICK", text=None, fingerprint="z"))
    assert len(history.recent()) == 10


class _ScriptedSession:
    def __init__(self, results: list[ActResult]) -> None:
        self.results: list[ActResult] = results
        self.calls: int = 0

    def act(self, instruction: str, /, **kwargs: Any) -> ActResult:
        assert kwargs["raise_on_failure"] is False
        self.calls += 1
        return self.results.pop(0)


def _result(status: str = "executed", fingerprint: str = "a", operation: str = "CLICK") -> ActResult:
    return ActResult.model_validate(
        {"instruction": "go", "status": status, "fingerprint": fingerprint, "operation": operation}
    )


def test_act_until_done_stops_on_done() -> None:
    session = _ScriptedSession([_result(fingerprint="a"), _result(fingerprint="b"), _result("done", "c")])
    assert [r.status for r in act_until_done(session, "go")] == ["executed", "executed", "done"]


def test_act_until_done_stops_after_three_unchanged_actions() -> None:
    session = _ScriptedSession([_result(fingerprint="a") for _ in range(10)])
    results = act_until_done(session, "go")
    # the 4th decision sees the same page as the first: 3 actions changed nothing
    assert len(results) == 4


def test_act_until_done_ignores_waits_and_respects_the_budget() -> None:
    session = _ScriptedSession([_result(fingerprint="a", operation="WAIT") for _ in range(10)])
    assert len(act_until_done(session, "go", max_steps=6)) == 6


def test_act_errors_rehydrate_from_their_serialized_form() -> None:
    from notte_core.act import InvalidDecisionError, NoActionFoundError
    from notte_core.observation import SerializedError

    error = SerializedError.from_exception(NoActionFoundError("go", "blocked")).to_exception()
    assert isinstance(error, NoActionFoundError) and error.result is None and "go" in error.dev_message
    retry = SerializedError.from_exception(InvalidDecisionError("bad")).to_exception()
    assert isinstance(retry, InvalidDecisionError) and retry.should_retry_later


def test_signature_includes_the_frame_path() -> None:
    from notte_core.dom_tree import NodeSelectors

    def page(frames: list[str]) -> ObservedPage:
        selectors = NodeSelectors(
            css_selector="button",
            xpath_selector="html/body/button",
            in_iframe=True,
            in_shadow_root=False,
            iframe_parent_css_selectors=frames,
        )
        actions = [ClickAction(id="B1", text_label="Submit", selector=selectors)]
        return _page(states={}, actions=actions)

    # the same button in another frame is another target
    assert page(["iframe#a"]).signature("B1") != page(["iframe#b"]).signature("B1")


def test_truncated_select_options_can_be_typed() -> None:
    options = (SelectOption(value="v0", label="Option 0", selected=True), SelectOption(value="v1", label="Option 1"))
    states = {"I3": ElementState(value="v0", options=options, options_truncated=True)}
    space = build_act_space(_page(states=states))
    element = next(e for e in space.elements if e["index"] == "I3")
    assert element["more_options"] is True
    assert set(space.targets["SELECT"]) == {"I3:1"}
    # the options left out of the live state are reachable by typing their label
    assert space.targets["TYPE_TEXT"]["I3"].kind == "select_text"


def test_multiple_select_is_flagged() -> None:
    options = (SelectOption(value="a", label="A"), SelectOption(value="b", label="B"))
    space = build_act_space(_page(states={"I3": ElementState(options=options, multiple=True)}))
    assert next(e for e in space.elements if e["index"] == "I3")["multiple"] is True


def test_act_until_done_does_not_count_scrolls_as_unchanged() -> None:
    session = _ScriptedSession([_result(fingerprint="a", operation="SCROLL_DOWN") for _ in range(10)])
    assert len(act_until_done(session, "go", max_steps=7)) == 7


def _signature(tag: str, text: str, value: Any = None, checked: Any = None, options: Any = None) -> list[Any]:
    return [tag, text, value, checked, None, None, None, None, None, None, None, None, None, None, options, []]


def test_signature_baseline_must_match_the_observation() -> None:
    from notte_core.act.freshness import Signatures

    page = _page()
    current = Signatures(
        {
            "url": page.url,
            "elements": {
                "B1": _signature("BUTTON", "SIGN IN"),
                "I1": _signature("INPUT", "", value="jane@"),
                "I2": _signature("INPUT", "", checked=False),
                "I3": _signature(
                    "SELECT",
                    "",
                    value="us",
                    options=[[o.value, o.label, o.selected, o.disabled] for o in STATES["I3"].options or ()],
                ),
            },
        }
    )
    assert all(current.consistent(page, element_id) for element_id in ("B1", "I1", "I2", "I3"))

    changed = Signatures(
        {
            "url": page.url,
            "elements": {
                # changed between the observation and the baseline read
                "B1": _signature("BUTTON", "Delete account"),
                "L1": _signature("BUTTON", "Help"),
                "I1": _signature("INPUT", "", value="other"),
                "I2": _signature("INPUT", "", checked=True),
                "I3": _signature("SELECT", "", value="fr", options=[["fr", "France", True, False]]),
            },
        }
    )
    assert not any(changed.consistent(page, element_id) for element_id in ("B1", "L1", "I1", "I2", "I3"))
    assert not changed.consistent(page, "missing")


@pytest.mark.asyncio
async def test_vault_secrets_typed_earlier_are_masked() -> None:
    from notte_core.act import run_act
    from notte_core.observation import ExecutionResult

    from tests.act.fakes import FakeDecider

    vault_email = "jane.private@example.test"
    page = _page(
        states={"I1": ElementState(value=vault_email)}, description=DESCRIPTION + f"\n_[:]Signed in as {vault_email}"
    )

    class Driver:
        has_vault: bool = True

        def secret_replacements(self) -> dict[str, str]:
            return {vault_email: "user@example.org"}

        async def observe(self, observation: Any) -> ObservedPage:  # pyright: ignore[reportUnusedParameter]
            return page

        async def is_fresh(self, page: ObservedPage, element_id: str | None, *, focus: bool = False) -> bool:  # pyright: ignore[reportUnusedParameter]
            return True

        async def execute(self, action: Any, raise_on_failure: bool) -> ExecutionResult:  # pyright: ignore[reportUnusedParameter]
            raise AssertionError("not executed")

    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await run_act(Driver(), decider, ActHistory(), "check the account", raise_on_failure=False)
    assert vault_email not in decider.states[0].model_dump_json()
    assert "user@example.org" in decider.states[0].model_dump_json()


@pytest.mark.asyncio
async def test_choose_masks_protected_options() -> None:
    from notte_core.act import run_choose

    from tests.act.fakes import FakeDecider

    email = "jane.private@example.test"
    page = _page()

    class Driver:
        has_vault: bool = False

        def secret_replacements(self) -> dict[str, str]:
            return {}

        async def observe(self, observation: Any) -> ObservedPage:  # pyright: ignore[reportUnusedParameter]
            return page

    history = ActHistory()
    history.privacy.remember({"email": email})
    decider = FakeDecider(choices=[{"answer": "{{email}}"}, {"answer": "option 2"}])
    choice = await run_choose(Driver(), decider, history, "Which account is shown?", [email, "another account"])  # pyright: ignore[reportArgumentType]
    assert email not in decider.questions[0]["answer"].model_dump_json()
    assert choice.choice == email and set(choice.probabilities) == {email, "another account"}

    # masked, both would be "{{email}}": numbered instead
    choice = await run_choose(Driver(), decider, history, "Which one?", ["{{email}}", email])  # pyright: ignore[reportArgumentType]
    assert list(decider.questions[1]["answer"].criteria) == ["option 1", "option 2"]
    assert email not in decider.questions[1]["answer"].model_dump_json()
    assert choice.choice == email


ACCESSIBLE_DESCRIPTION = """### Content of 'WebArea' component with text 'body content'
_[:]Sign in to Example
_[:]Username or email address
I1[:]<input type="text" name="login"></input>
I2[:]<input type="checkbox" name="remember"></input>
_[:]Keep me signed in
I3[:]<select name="country"></select>
I4[:]<input type="search" aria_label="Search the docs" placeholder="Search"></input>
B1[:]<input type="submit" value="Sign in" name="commit"></input>
B2[:]<button type="button">Sign in with
a passkey</button>
L1[:]<a href="/help"></a>
_[:]A sentence that is far too long to be the label of the field right after it, so it is not used as one.
I5[:]<input type="text" name="code" placeholder="123456"></input>
### Content of 'dialog' component with text 'Cookies'
B3[:]<button>Accept</button>"""


def _accessible_page(**kwargs: Any) -> ObservedPage:
    actions: list[InteractionAction] = [
        FillAction(id="I1", value="<sample_value>", text_label="login"),
        CheckAction(id="I2", value=True, text_label="remember"),
        SelectDropdownOptionAction(id="I3", value="<sample_value>", text_label="country"),
        FillAction(id="I4", value="<sample_value>", text_label="Search the docs"),
        ClickAction(id="B1", text_label="commit"),
        ClickAction(id="B2", text_label="Sign in with a passkey"),
        ClickAction(id="L1", text_label=""),
        FillAction(id="I5", value="<sample_value>", text_label="code"),
        ClickAction(id="B3", text_label="Accept"),
    ]
    return _page(description=ACCESSIBLE_DESCRIPTION, actions=actions, states={}, **kwargs)


def test_accessible_names_without_names_in_the_observation_are_approximated() -> None:
    # an older server's observation: no `accessible_name`, so names come from the rendered page
    assert accessible_names(_accessible_page()) == {
        # the label text before a field, after a checkbox (notte's text_label is the name attribute)
        "I1": "Username or email address",
        "I2": "Keep me signed in",
        "I3": "country",
        # aria-label first; a submit input is its value; a multi-line button its whole text
        "I4": "Search the docs",
        "B1": "Sign in",
        "B2": "Sign in with a passkey",
        # an unnamed link is its destination
        "L1": "/help",
        # a long text is not a label: the placeholder is used
        "I5": "123456",
        "B3": "Accept",
    }


LABELS = """M1[:]<label>Username</label>
I1[:]<input type="text" name="username"></input>
I2[:]<input type="checkbox" name="remember"></input>
M2[:]<label>Remember me</label>
M3[:]<label>Stay hidden</label>
I3[:]<input type="text" name="code"></input>
L1[:]<a href="/help"></a>"""


def _labels_page(named: bool) -> ObservedPage:
    def name(value: str) -> str | None:
        return value if named else None

    actions: list[InteractionAction] = [
        ClickAction(id="M1", text_label="Username", accessible_name=name("Username")),
        FillAction(id="I1", value="<sample_value>", text_label="username", accessible_name=name("Username")),
        CheckAction(id="I2", value=True, text_label="remember", accessible_name=name("Remember me")),
        ClickAction(id="M2", text_label="Remember me", accessible_name=name("Remember me")),
        # the visible label of a hidden custom checkbox, right before an unrelated field
        ClickAction(id="M3", text_label="Stay hidden", accessible_name=name("Stay hidden")),
        FillAction(id="I3", value="<sample_value>", text_label="code", accessible_name=name("One-time code")),
        # unnamed in the observation: the approximation fills in
        ClickAction(id="L1", text_label=""),
    ]
    return _page(description=LABELS, actions=actions, states={})


def test_the_observations_accessible_names_label_the_elements() -> None:
    page = _labels_page(named=True)
    assert accessible_names(page) == {
        "I1": "Username",
        "I2": "Remember me",
        "M3": "Stay hidden",
        # the real name, not the label-like text next to it
        "I3": "One-time code",
        "L1": "/help",
    }
    # a `<label>` whose text is the name of the field next to it labels that field: neither offered nor
    # repeated. A label that names nothing offered (M3) stays, it may be the only way to toggle a control.
    assert label_elements(page) == {"M1", "M2"}
    space = build_act_space(page, labels="accessible")
    assert [e["index"] for e in space.elements] == ["I1", "I2", "M3", "I3", "L1"]
    assert not any(key in ("M1", "M2") for targets in space.targets.values() for key in targets)
    assert accessible_text(page).splitlines() == [
        "[I1] Username",
        "[I2] Remember me",
        "[M3] Stay hidden",
        "[I3] One-time code",
        "[L1] /help",
    ]
    criteria = act_questions(space, "sign in")["type_text_target"].criteria["I3"]
    assert criteria["element"] == "[I3] One-time code"
    # html mode keeps every element: the `<label>` markup says what it is
    assert {"M1", "M2"} <= {e["index"] for e in build_act_space(page, labels="html").elements}


def test_without_names_labels_stay_elements() -> None:
    # an older server: a label's text may be taken as the next field's name, so the label stays offered
    page = _labels_page(named=False)
    assert label_elements(page) == frozenset()
    names = accessible_names(page)
    assert names["I1"] == "Username" and names["I3"] == "Stay hidden" and names["M1"] == "Username"
    assert {"M1", "M2", "M3"} <= {e["index"] for e in build_act_space(page, labels="accessible").elements}


def test_accessible_mode_labels_elements_and_targets_without_html() -> None:
    space = build_act_space(_accessible_page(), labels="accessible")
    elements = {e["index"]: e for e in space.elements}
    assert elements["I1"]["label"] == "Username or email address" and elements["I1"]["role"] == "textbox"
    assert elements["I2"]["label"] == "Keep me signed in" and elements["I2"]["role"] == "checkbox"
    # the name is the element's text: no separate `text`
    assert all("text" not in e for e in space.elements)
    assert all("<" not in e["label"] for e in space.elements)
    criteria = act_questions(space, "sign in")["type_text_target"].criteria["I1"]
    assert criteria == {"element": "[I1] Username or email address", "current_value": "", "role": "textbox"}
    # roles and operations come from the HTML, whatever the labels
    html = build_act_space(_accessible_page())
    assert {k: set(v) for k, v in space.targets.items()} == {k: set(v) for k, v in html.targets.items()}
    assert elements["I1"]["operations"] == next(e for e in html.elements if e["index"] == "I1")["operations"]


def test_accessible_mode_keeps_live_state_and_select_options() -> None:
    space = build_act_space(_page(), labels="accessible")
    elements = {e["index"]: e for e in space.elements}
    assert elements["I1"]["label"] == "Sign in" and elements["I1"]["value"] == "jane@"
    assert elements["I3"]["options"][1] == {"index": "I3:2", "label": "France", "value": "fr"}
    criteria = act_questions(space, "sign in")["select_target"].criteria["I3:2"]
    assert criteria["element"] == "[I3:2] country → France" and criteria["current_value"] == "United States"


def test_accessible_text_is_visible_text_with_element_markers() -> None:
    text = accessible_text(_accessible_page())
    assert text.splitlines()[:4] == [
        "Sign in to Example",
        # a text that names the element next to it is not repeated as its own line
        "[I1] Username or email address",
        "[I2] Keep me signed in",
        "[I3] country",
    ]
    # a long text names nothing: it stays
    assert "A sentence that is far too long" in text
    assert "[B2] Sign in with a passkey" in text and "[L1] /help" in text
    # no markup, no page header; a dialog header says a modal is open
    assert "<" not in text and "[:]" not in text and "WebArea" not in text
    assert "Content of 'dialog' component with text 'Cookies'" in text
    assert page_state(_accessible_page(), "accessible").text == text
    assert page_state(_accessible_page(), "html").text == ACCESSIBLE_DESCRIPTION


def test_accessible_text_masks_names() -> None:
    page = _accessible_page()
    text = accessible_text(page, display_text=lambda s: s.replace("Sign in", "{{x}}"))
    assert "[B1] {{x}}" in text


def test_label_mode_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTTE_ACT_LABELS", raising=False)
    assert label_mode() == "accessible"
    monkeypatch.setenv("NOTTE_ACT_LABELS", "")
    assert label_mode() == "accessible"
    monkeypatch.setenv("NOTTE_ACT_LABELS", " HTML ")
    assert label_mode() == "html"
    monkeypatch.setenv("NOTTE_ACT_LABELS", "aria")
    with pytest.raises(ValueError, match="NOTTE_ACT_LABELS"):
        _ = label_mode()


def test_a_select_without_live_state_keeps_its_options_in_the_text() -> None:
    description = """_[:]Country
I1[:]<select name="country">Alpha
Beta</select>"""
    actions: list[InteractionAction] = [
        SelectDropdownOptionAction(id="I1", value="<sample_value>", text_label="country")
    ]
    stateless = _page(description=description, actions=actions, states={})
    assert accessible_text(stateless) == "[I1] Country (options: Alpha, Beta)"
    # with live state the options are SELECT targets: not repeated in the text
    state = ElementState(
        value="a",
        options=(SelectOption(value="a", label="Alpha", selected=True), SelectOption(value="b", label="Beta")),
    )
    local = _page(description=description, actions=actions, states={"I1": state})
    assert accessible_text(local) == "[I1] Country"


def test_a_variable_cut_by_the_browser_is_masked() -> None:
    history = ActHistory()
    token = "tok-" + "z" * 40
    history.privacy.remember({"token": token})
    # the browser cut the field value 10 characters into the token
    cut = "x" * 190 + token[:10]
    page = _page(states={"I1": ElementState(value=cut, value_truncated=True)})
    space = build_act_space(
        page, display_text=history.privacy.text, labels="accessible", display_cut=history.privacy.cut_text
    )
    value = next(e for e in space.elements if e["index"] == "I1")["value"]
    assert value == "x" * 190 + "{{token}}" and token[:10] not in value
    # an uncut value is masked as before, and ordinary text is left alone
    assert history.privacy.cut_text("plain") == "plain"


def test_past_the_cap_the_elements_in_view_are_offered_first() -> None:
    from notte_core.act.space import MAX_ELEMENTS

    actions: list[InteractionAction] = [
        ClickAction(id=f"B{i}", text_label=f"b{i}") for i in range(1, MAX_ELEMENTS + 51)
    ]
    description = "\n".join(f"{a.id}[:]<button>{a.text_label}</button>" for a in actions)
    # the last 10 buttons are in the viewport (the page is scrolled to its end)
    in_view = frozenset(a.id for a in actions[-10:])
    page = _page(description=description, actions=actions, states={}, in_view=in_view)
    offered = [e["index"] for e in build_act_space(page, labels="accessible").elements]
    assert len(offered) == MAX_ELEMENTS and in_view <= set(offered)
    # page order is kept: the first ones fill the rest
    assert offered[: MAX_ELEMENTS - 10] == [a.id for a in actions[: MAX_ELEMENTS - 10]]
    # under the cap, everything is offered
    small = _page(description=description, actions=actions[:20], states={})
    assert len(build_act_space(small, labels="accessible").elements) == 20


# an observation that describes disabled controls: without an id, with a `disabled` attribute
DISABLED_DESCRIPTION = """### Content of 'WebArea' component with text 'body content'
_[:]Name
_[:]<input disabled></input>
B1[:]<button>Enable</button>
_[:]<button disabled>Submit</button>
_[:]<input placeholder="City" name="city" disabled></input>
_[:]<button disabled>Save</button>
_[:]Email
I1[:]<input type="text" name="email"></input>"""


@pytest.mark.parametrize("named", [True, False])
def test_disabled_controls_are_shown_without_operations(named: bool) -> None:
    actions: list[InteractionAction] = [
        ClickAction(id="B1", text_label="Enable", accessible_name="Enable" if named else None),
        FillAction(id="I1", value="", text_label="email", accessible_name="Email" if named else None),
    ]
    page = _page(states={}, description=DISABLED_DESCRIPTION, actions=actions)

    assert accessible_text(page).splitlines() == [
        # an unnamed disabled field is shown by its role, after the text before it
        "Name",
        "textbox (disabled)",
        "[B1] Enable",
        "Submit (disabled)",
        "City (disabled)",
        "Save (disabled)",
        "[I1] Email",
    ]
    # offered: the enabled controls only
    assert [e["index"] for e in build_act_space(page, labels="accessible").elements] == ["B1", "I1"]
    # a disabled control does not name the field after it
    assert accessible_names(page)["I1"] == "Email"


def test_a_disabled_control_is_not_the_label_of_the_next_field() -> None:
    description = """### Content of 'WebArea' component with text 'body content'
_[:]<button disabled>Search</button>
I1[:]<input type="text" name="q"></input>"""
    page = _page(states={}, description=description, actions=[FillAction(id="I1", value="", text_label="q")])
    # without real names, the text before a field names it; a disabled button's markup does not
    assert accessible_names(page)["I1"] != "Search" and "<button" not in accessible_names(page)["I1"]
    assert accessible_text(page).splitlines() == ["Search (disabled)", f"[I1] {accessible_names(page)['I1']}"]


def test_a_dialog_hides_the_page_only_without_the_page_component() -> None:
    dialog = """### Content of 'dialog' component with text 'Cookies'
_[:]We use cookies
B1[:]<button>Accept all</button>"""
    assert covered_by_dialog(dialog)
    # the page itself, with or without its header, is not covered
    assert not covered_by_dialog(ACCESSIBLE_DESCRIPTION) and not covered_by_dialog(DESCRIPTION)
    page = _page(description=dialog, actions=[ClickAction(id="B1", text_label="Accept all")], states={})
    for labels in ("accessible", "html"):
        assert page_state(page, labels).text.splitlines()[0] == DIALOG_COVERS_PAGE


def _scrolled_page(description: str, actions: list[InteractionAction], scroll_y: int, **kwargs: Any) -> ObservedPage:
    """A page 20 viewports tall, scrolled to `scroll_y`."""
    viewport = ViewportData(
        scroll_x=0, scroll_y=scroll_y, viewport_width=1280, viewport_height=720, total_width=1280, total_height=14_400
    )
    return _page(description=description, actions=actions, states={}, viewport=viewport, **kwargs)


def _paragraphs(first: int, count: int) -> list[str]:
    return [f"_[:]Paragraph {i}: " + "lorem ipsum dolor sit amet " * 6 for i in range(first, first + count)]


@pytest.mark.parametrize("labels", ["accessible", "html"])
def test_page_text_says_what_is_below_the_viewport(labels: Any) -> None:
    # only the elements in the viewport are offered: a link further down is plain text
    description = "\n".join(
        ["L1[:]<a href='#a'>Top link</a>", *_paragraphs(0, 3), *_paragraphs(3, 40), "_[:]Bottom link"]
    )
    page = _scrolled_page(description, [ClickAction(id="L1", text_label="Top link")], scroll_y=0)
    text = page_state(page, labels).text
    assert [e["index"] for e in build_act_space(page, labels=labels).elements] == ["L1"]
    in_view, below = (
        text.index("--- in the viewport ---"),
        text.index("--- below the viewport: scroll down to reach ---"),
    )
    assert in_view < text.index("Top link") < below < text.index("Bottom link")
    assert "--- above the viewport ---" not in text


@pytest.mark.parametrize("labels", ["accessible", "html"])
def test_long_page_text_follows_the_scroll_position(labels: Any) -> None:
    from notte_core.act.space import MAX_PAGE_TEXT_LENGTH

    paragraphs = _paragraphs(0, 300)
    actions: list[InteractionAction] = [ClickAction(id="L1", text_label="Download the Q3 report")]
    bottom = "\n".join(["_[:]Annual review", *paragraphs, "L1[:]<a href='q3'>Download the Q3 report</a>"])
    top = "\n".join(["_[:]Annual review", *paragraphs, "_[:]Download the Q3 report"])

    at_top = page_state(_scrolled_page(top, [], scroll_y=0), labels).text
    middle = page_state(_scrolled_page(top, [], scroll_y=7_200), labels).text
    at_bottom = page_state(_scrolled_page(bottom, actions, scroll_y=13_680), labels).text
    for text in (at_top, middle, at_bottom):
        assert len(text) <= MAX_PAGE_TEXT_LENGTH
    assert "Annual review" in at_top and "Paragraph 150:" not in at_top
    # halfway down the page, the text is halfway down the page too
    assert "Annual review" not in middle and "Paragraph 150:" in middle
    assert middle.index("--- above the viewport ---") < middle.index("--- in the viewport ---")
    # at the bottom, the link in view and the text around it, not the top of the page
    assert "Annual review" not in at_bottom and "Download the Q3 report" in at_bottom
    assert at_bottom.startswith("...\n--- above the viewport ---")


def test_a_sticky_header_does_not_pull_the_page_text_to_the_top() -> None:
    # a header that stays in view (sticky) is at the top of the text, the content scrolled to at the bottom
    description = "\n".join(
        ["B1[:]<button>Main menu</button>", *_paragraphs(0, 300), "L1[:]<a href='#next'>Next chapter</a>"]
    )
    actions: list[InteractionAction] = [
        ClickAction(id="B1", text_label="Main menu"),
        ClickAction(id="L1", text_label="Next chapter"),
    ]
    text = page_state(_scrolled_page(description, actions, scroll_y=13_680), "accessible").text
    assert "[L1] Next chapter" in text and "Paragraph 299:" in text and "Paragraph 0:" not in text


def test_page_text_is_unmarked_when_it_is_all_in_view() -> None:
    page = _scrolled_page(DESCRIPTION, _actions(), scroll_y=0)
    assert page_state(page, "html").text == DESCRIPTION
    # and on a page that fits in the viewport
    assert page_state(_page(viewport=None), "html").text == DESCRIPTION


@pytest.mark.parametrize("labels", ["accessible", "html"])
def test_an_action_is_decided_on_the_text_in_view(labels: Any) -> None:
    # the decider is offered the elements in view: it reads the text in view, and that there is more
    paragraphs = _paragraphs(0, 300)
    description = "\n".join(["_[:]Annual review", *paragraphs, "_[:]Download the Q3 report"])
    top = page_state(_scrolled_page(description, [], scroll_y=0), labels, viewport_only=True).text
    middle = page_state(_scrolled_page(description, [], scroll_y=7_200), labels, viewport_only=True).text
    assert "Annual review" in top.splitlines()[0] and "Paragraph 150:" not in top
    assert top.endswith("characters of page text below the viewport not shown: scroll down to read them)")
    assert middle.startswith("(page text above the viewport not shown: scroll up to read it)")
    assert "Paragraph 150:" in middle and "Annual review" not in middle and "Download the Q3 report" not in middle
    assert len(middle) < len("\n".join(paragraphs)) / 10

    near = "\n".join(["L1[:]<a href='#a'>Top link</a>", *_paragraphs(0, 40), "_[:]Bottom link"])
    page = _scrolled_page(near, [ClickAction(id="L1", text_label="Top link")], scroll_y=0)
    text = page_state(page, labels, viewport_only=True).text
    assert "Top link" in text and "Bottom link" not in text


def test_disabled_controls_and_the_dialog_line_compose_with_the_viewport_text() -> None:
    filler = "\n".join(f"_[:]Paragraph {i}: " + "lorem ipsum dolor sit amet " * 8 for i in range(60))
    description = f"""### Content of 'WebArea' component with text 'body content'
{filler}
_[:]Shipping
B1[:]<button>Edit address</button>
_[:]<button disabled>Pay now</button>
I1[:]<input type="text" name="coupon"></input>"""
    actions: list[InteractionAction] = [
        ClickAction(id="B1", text_label="Edit address", accessible_name="Edit address"),
        FillAction(id="I1", value="", text_label="coupon", accessible_name="Coupon"),
    ]
    page = _scrolled_page(description, actions, scroll_y=13_680, in_view=frozenset({"B1", "I1"}))
    # the decision text: the viewport only, with the disabled control in it
    text = page_state(page, "accessible", viewport_only=True).text.splitlines()
    assert text[-4:] == ["Shipping", "[B1] Edit address", "Pay now (disabled)", "[I1] Coupon"]
    assert not any(line.startswith("Paragraph 1:") for line in text)

    # a dialog over the page: the dialog line first, whatever part of the text is shown
    dialog = """### Content of 'dialog' component with text 'Confirm'
_[:]Are you sure?
_[:]<button disabled>Confirm</button>
B1[:]<button>Cancel</button>"""
    page = _scrolled_page(dialog, [ClickAction(id="B1", text_label="Cancel", accessible_name="Cancel")], 13_680)
    for labels in ("accessible", "html"):
        lines = page_state(page, labels, viewport_only=True).text.splitlines()
        assert lines[0] == DIALOG_COVERS_PAGE
    assert "Confirm (disabled)" in page_state(page, "accessible", viewport_only=True).text


def test_unnamed_checkboxes_are_named_by_the_text_next_to_them() -> None:
    # a list whose checkboxes have no accessible name (the item text is not their label)
    description = """### Content of 'WebArea' component with text 'body content'
_[:]todos
I1[:]<input type="text" name="new"></input>
B1[:]<input type="checkbox"></input>
_[:]buy milk
B2[:]<button>Delete</button>
B3[:]<input type="checkbox"></input>
_[:]walk the dog"""
    actions: list[InteractionAction] = [
        FillAction(id="I1", value="", text_label="new", accessible_name="New todo"),
        CheckAction(id="B1", value=True, text_label=""),
        ClickAction(id="B2", text_label="Delete", accessible_name="Delete"),
        CheckAction(id="B3", value=True, text_label=""),
    ]
    page = _page(states={}, description=description, actions=actions)
    names = accessible_names(page)
    assert names["B1"] == "buy milk" and names["B3"] == "walk the dog"
    # the field is not named by the heading before it
    assert names["I1"] == "New todo"
    assert accessible_text(page).splitlines() == [
        "todos",
        "[I1] New todo",
        "[B1] buy milk",
        "[B2] Delete",
        "[B3] walk the dog",
    ]


def test_a_read_only_combobox_from_the_signatures_is_typed_by_option_label() -> None:
    from dataclasses import replace

    from notte_core.act.freshness import Signatures

    description = """### Content of 'WebArea' component with text 'body content'
_[:]Country
I1[:]<input role="combobox"></input>"""
    # a combobox: a select action on an element that is not a `<select>`
    action = SelectDropdownOptionAction(id="I1", value="<sample_value>", text_label="", accessible_name="Country")
    page = _page(states={}, description=description, actions=[action])
    readonly = _signature("INPUT", "", value="")
    readonly[12] = True
    signatures = Signatures({"url": page.url, "elements": {"I1": readonly}})
    assert signatures.readonly() == {"I1"}

    def kind(page: ObservedPage) -> Any:
        target = build_act_space(page, labels="accessible").targets["TYPE_TEXT"]["I1"]
        return type(target_action(target, "France")).__name__

    # the rendered page does not show `readonly`: without the signatures the input is filled
    assert kind(page) == "FillAction"
    assert kind(replace(page, readonly=signatures.readonly())) == "SelectDropdownOptionAction"


COOKIE_DIALOG = """### Content of 'dialog' component with text ''
_[:]We value your privacy
_[:]We use cookies to improve your experience.
B1[:]<button type="button">Accept all</button>
B2[:]<button type="button">Reject all</button>
I1[:]<input type="checkbox" name="analytics"></input>
_[:]Analytics cookies
I2[:]<input type="text" name="q" role="combobox"></input>"""


def test_closing_a_dialog_over_the_page_is_an_operation_of_its_own() -> None:
    actions: list[InteractionAction] = [
        ClickAction(id="B1", text_label="Accept all", accessible_name="Accept all"),
        ClickAction(id="B2", text_label="Reject all", accessible_name="Reject all"),
        CheckAction(id="I1", value=True, text_label="analytics", accessible_name="Analytics cookies"),
        SelectDropdownOptionAction(id="I2", value="<sample_value>", text_label="", accessible_name="Search"),
    ]
    page = _page(states={}, description=COOKIE_DIALOG, actions=actions)
    space = build_act_space(page, labels="accessible")
    # the dialog's buttons close it; a toggle or a field inside it (a search box) does not
    assert set(space.targets["CLOSE_DIALOG"]) == {"B1", "B2"}
    assert "CLOSE_DIALOG" in space.operations
    questions = act_questions(space, "Open the Pricing page")
    assert set(questions["close_dialog_target"].criteria) == {"B1", "B2"}
    elements = {e["index"]: e for e in space.elements}
    assert (
        elements["B1"]["operations"] == ["CLICK", "CLOSE_DIALOG"] and "CLOSE_DIALOG" not in elements["I1"]["operations"]
    )

    # answered like any target operation, executed as a click on the chosen button
    answers = Answers(
        answers={
            "operation": Answer(
                choice="CLOSE_DIALOG", probabilities=_spread(space.operations, "CLOSE_DIALOG"), confidence=0.9
            ),
            "close_dialog_target": Answer(choice="B2", probabilities={"B1": 0.2, "B2": 0.8}, confidence=0.8),
        },
        model="fake",
    )
    decision = interpret(answers, space)
    assert decision.target is not None
    action = target_action(decision.target, None)
    assert isinstance(action, ClickAction) and action.id == "B2"


def test_a_page_without_a_dialog_has_no_close_operation() -> None:
    space = build_act_space(_page(), labels="accessible")
    assert "CLOSE_DIALOG" not in space.operations and "CLOSE_DIALOG" not in space.targets


def _spread(keys: Any, choice: str) -> dict[str, float]:
    rest = 0.1 / (len(keys) - 1)
    return {k: 0.9 if k == choice else rest for k in keys}


def test_field_context_reads_the_text_before_a_field() -> None:
    from notte_core.act.space import field_context

    description = """_[:]State and City
_[:]Select State
I1[:]<select>A
B</select>
_[:]Select City
I2[:]<input type="text" role="combobox" placeholder="Type a city"></input>"""
    actions: list[InteractionAction] = [
        SelectDropdownOptionAction(id="I1", value="<sample_value>", text_label="A B", accessible_name="State"),
        FillAction(id="I2", value="<sample_value>", text_label="", accessible_name=""),
    ]
    page = _page(description=description, actions=actions, states={})
    assert field_context(page, "I1", "accessible", exclude="State") == {"nearby": "State and City / Select State"}
    # the unnamed combobox is named by the text before it, so that text is its label, not nearby text
    assert accessible_names(page)["I2"] == "Select City"
    assert field_context(page, "I2", "accessible", exclude="Select City") == {"placeholder": "Type a city"}
    # the rendered page: a select's option lines are not text before the next field
    assert field_context(page, "I2", "html", exclude="combobox") == {
        "placeholder": "Type a city",
        "nearby": "Select City",
    }


def test_an_empty_suggestion_list_is_not_shown() -> None:
    # a search box's popup after typing a query it has no suggestions for: an empty listbox, no option after it
    description = """### Content of 'dialog' component with text 'Quick search'
_[:]Quick search
I1[:]<input value="pallets/flask" role="combobox" aria_label="Search or jump to" aria_expanded="false"></input>
I2[:]<ul role="listbox" aria_label="Search suggestions"></ul>
L1[:]<a href="/tips">Search syntax tips</a>
I3[:]<ul role="listbox" aria_label="Recent"></ul>"""
    actions: list[InteractionAction] = [
        SelectDropdownOptionAction(id="I1", value="<sample_value>", accessible_name="Search or jump to"),
        FillAction(id="I2", value="<sample_value>", text_label="", accessible_name="Search suggestions"),
        ClickAction(id="L1", text_label="Search syntax tips", accessible_name="Search syntax tips"),
        FillAction(id="I3", value="<sample_value>", text_label="", accessible_name="Recent"),
    ]
    page = _page(description=description, actions=actions, states={"I1": ElementState(value="pallets/flask")})
    for labels in ("accessible", "html"):
        space = build_act_space(page, labels=labels)
        assert [e["index"] for e in space.elements] == ["I1", "L1"]
        text = page_state(page, labels).text
        assert "Search suggestions" not in text and "Recent" not in text and "Search syntax tips" in text

    # with its suggestions (options right after it), the list is shown
    listed = description.replace("\nL1[:]", '\nO1[:]<li role="option">pallets/flask</li>\nL1[:]')
    actions.append(SelectDropdownOptionAction(id="O1", value="<sample_value>", accessible_name="pallets/flask"))
    page = _page(description=listed, actions=actions, states={})
    elements = [e["index"] for e in build_act_space(page, labels="accessible").elements]
    assert "I2" in elements and "O1" in elements and "I3" not in elements
    assert "[I2] Search suggestions" in accessible_text(page)


def test_typing_changed_the_page_beyond_the_field() -> None:
    from notte_core.act.space import changed_beyond, find_field

    def issues(query: str, results: list[str]) -> ObservedPage:
        # the query is also rendered next to the field (a highlighted copy, spaced differently)
        lines = [
            "_[:]Search issues",
            f"_[:]{' : '.join(query.split(':'))}",
            'I1[:]<input aria_label="Search issues"></input>',
        ]
        lines += [f'L{i}[:]<a href="/{i}">{r}</a>' for i, r in enumerate(results, 1)]
        actions: list[InteractionAction] = [FillAction(id="I1", value="<sample_value>", text_label="Search issues")]
        actions += [ClickAction(id=f"L{i}", text_label=r) for i, r in enumerate(results, 1)]
        return _page(description="\n".join(lines), actions=actions, states={"I1": ElementState(value=query)})

    before = issues("is:open", ["Crash on start", "Typo in docs"])
    values = ["is:open label:bug", "is:open"]
    # only the copy of the query changed: the query is typed, not applied
    assert not changed_beyond(before, issues("is:open label:bug", ["Crash on start", "Typo in docs"]), "I1", values)
    # a result is gone: the field filtered the page as it was typed in
    assert changed_beyond(before, issues("is:open label:bug", ["Crash on start"]), "I1", values)
    assert find_field(before, "Search issues", "is:open") == "I1"
    assert find_field(before, "Search issues", "is:closed") is None
