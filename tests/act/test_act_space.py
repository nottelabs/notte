"""The model-agnostic part of `act()`: questions built from an observed page, strict answer validation,
mapping answers to notte actions, history and the loop helper. No browser, no model."""

from typing import Any

import pytest
from notte_core.act import ActHistory, ActResult, Answer, Answers, ObservedPage, act_until_done
from notte_core.act.errors import InvalidDecisionError
from notte_core.act.space import (
    act_questions,
    build_act_space,
    description_lines,
    interpret,
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
