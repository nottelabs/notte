"""The model-agnostic part of `act()`: questions built from an observed page, strict answer validation,
mapping answers to notte actions, history and the loop helper. No browser, no model."""

from typing import Any

import pytest
from notte_core.act import ActHistory, ActResult, Answer, Answers, ObservedPage, act_until_done
from notte_core.act.errors import InvalidDecisionError
from notte_core.act.space import (
    accessible_names,
    accessible_text,
    act_questions,
    build_act_space,
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
    # remote sessions: no state, a native select is set by typing its option label
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
    history.observed("b")
    history.entries.append(ActHistoryEntry(action="Help", kind="CLICK", text=None, fingerprint="b"))
    history.observed("b")
    history.entries.append(ActHistoryEntry(action="x", kind="TYPE_TEXT", text="t", fingerprint="b", pending=False))
    history.observed("c")
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
    return [tag, text, value, checked, None, None, None, None, None, None, None, None, None, None, options]


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

        async def is_fresh(self, page: ObservedPage, element_id: str | None) -> bool:  # pyright: ignore[reportUnusedParameter]
            return True

        async def execute(self, action: Any, raise_on_failure: bool) -> ExecutionResult:  # pyright: ignore[reportUnusedParameter]
            raise AssertionError("not executed")

    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = await run_act(Driver(), decider, ActHistory(), "check the account", raise_on_failure=False)
    assert vault_email not in decider.states[0].model_dump_json()
    assert "user@example.org" in decider.states[0].model_dump_json()


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


def test_accessible_names_approximate_the_browser_names() -> None:
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


def test_a_clickable_label_names_the_field_next_to_it() -> None:
    # notte gives clickable `<label>` elements an id: they still name their field
    description = """M1[:]<label>Username</label>
I1[:]<input type="text" name="username"></input>
I2[:]<input type="checkbox" name="remember"></input>
M2[:]<label>Remember me</label>
I3[:]<input type="text" name="code"></input>"""
    actions: list[InteractionAction] = [
        ClickAction(id="M1", text_label="Username"),
        FillAction(id="I1", value="<sample_value>", text_label="username"),
        CheckAction(id="I2", value=True, text_label="remember"),
        ClickAction(id="M2", text_label="Remember me"),
        FillAction(id="I3", value="<sample_value>", text_label="code"),
    ]
    page = _page(description=description, actions=actions, states={})
    assert accessible_names(page) == {"I1": "Username", "I2": "Remember me", "I3": "code"}
    # the labels name their fields, so they are not offered as elements of their own (or repeated as text)
    assert label_elements(page) == {"M1", "M2"}
    space = build_act_space(page, labels="accessible")
    assert [e["index"] for e in space.elements] == ["I1", "I2", "I3"]
    assert not any(key in ("M1", "M2") for targets in space.targets.values() for key in targets)
    assert accessible_text(page).splitlines() == ["[I1] Username", "[I2] Remember me", "[I3] code"]
    # html mode keeps every element: the `<label>` markup says what it is
    assert {"M1", "M2"} <= {e["index"] for e in build_act_space(page, labels="html").elements}


def test_a_label_that_names_nothing_stays_clickable() -> None:
    # a custom checkbox: the visible label is the only way to toggle the hidden input
    description = """M1[:]<label>Remember me</label>
B1[:]<button>Login</button>"""
    actions: list[InteractionAction] = [
        ClickAction(id="M1", text_label="Remember me"),
        ClickAction(id="B1", text_label="Login"),
    ]
    page = _page(description=description, actions=actions, states={})
    assert label_elements(page) == frozenset()
    assert [e["index"] for e in build_act_space(page, labels="accessible").elements] == ["M1", "B1"]


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
