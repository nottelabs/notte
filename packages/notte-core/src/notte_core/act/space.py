# The operation / target split of the questions, the strict answer validation and the element
# indexing are adapted from jev-ultrafast (`jev_ultrafast/model.py`: `action_space`, `choose`,
# `validate_choice`), Copyright (c) 2026 Browser Use, MIT License (see `LICENSE-jev-ultrafast`).
"""Turn an observed page into the questions of `act()`, and the answers back into a notte action.

Every interaction action of the observation becomes an element, indexed by its notte id (`B1`, `I3`).
One `operation` question picks what to do (CLICK, TYPE_TEXT, SELECT, a control, DONE or BLOCKED),
and one target question per operation picks the element: only the target question of the chosen
operation is used, the others are ignored. Native `<select>` options (from the live element state)
are SELECT targets `<id>:<n>`.
"""

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import notte_core.act.prompts as prompts
from notte_core.act.errors import InvalidDecisionError
from notte_core.act.types import Answer, Answers, PageState, Question
from notte_core.actions import (
    BaseAction,
    CheckAction,
    ClickAction,
    FillAction,
    GoBackAction,
    InteractionAction,
    PressKeyAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    WaitAction,
)
from notte_core.element_state import ElementState, SelectOption, page_fingerprint
from notte_core.observation import Observation
from notte_core.snapshot import ViewportData

MAX_ELEMENTS = 250
MAX_LABEL_LENGTH = 300
MAX_PAGE_TEXT_LENGTH = 12_000
WAIT_MS = 1_000

Operation = Literal["CLICK", "TYPE_TEXT", "SELECT"]
TargetKind = Literal["click", "check", "fill", "select_option", "select_text"]

_DESCRIPTION_LINE = re.compile(r"^([A-Z]\d+)\[:\](.*)$")


@dataclass(frozen=True)
class ObservedPage:
    """What `act()` needs from one observation of the page (local or remote session)."""

    url: str
    title: str
    description: str
    actions: Sequence[InteractionAction]
    viewport: ViewportData | None
    # live element state by action id (empty for remote sessions: their observe response has none)
    states: Mapping[str, ElementState]
    fingerprint: str

    @staticmethod
    def from_observation(
        observation: Observation, states: Mapping[str, ElementState] | None = None, fingerprint: str | None = None
    ) -> "ObservedPage":
        """Wrap an observation. Without `fingerprint`, it hashes the URL and the actions' ids and labels."""
        actions = list(observation.space.interaction_actions)
        url = observation.metadata.url
        return ObservedPage(
            url=url,
            title=observation.metadata.title,
            description=observation.space.description,
            actions=actions,
            viewport=observation.metadata.viewport,
            states=states or {},
            fingerprint=fingerprint or page_fingerprint(url, ((a.id, a.text_label or "", None) for a in actions)),
        )

    def signature(self, element_id: str) -> str | None:
        """What a decision about `element_id` depends on: its type, label, selectors (including the iframe
        and shadow-root path used to execute it) and live state."""
        for action in self.actions:
            if action.id == element_id:
                selectors = action.selectors
                state = self.states.get(element_id)
                return "|".join(
                    [
                        action.type,
                        action.text_label or "",
                        "" if selectors is None else selectors.model_dump_json(),
                        "" if state is None else state.digest(),
                    ]
                )
        return None


@dataclass(frozen=True)
class Target:
    key: str
    element_id: str
    kind: TargetKind
    label: str
    criteria: dict[str, Any]
    option: SelectOption | None = None
    checked: bool | None = None
    role: str = ""
    value: str | None = None


@dataclass(frozen=True)
class Control:
    key: str
    label: str
    action: BaseAction


@dataclass
class ActSpace:
    elements: list[dict[str, Any]] = field(default_factory=list)
    targets: dict[str, dict[str, Target]] = field(default_factory=dict)
    controls: dict[str, Control] = field(default_factory=dict)

    @property
    def operations(self) -> dict[str, str]:
        operations = {key: prompts.OPERATION_LABELS[key] for key in self.targets}
        operations.update({key: control.label for key, control in self.controls.items()})
        operations.update(DONE=prompts.DONE, BLOCKED=prompts.BLOCKED)
        return operations


def description_lines(description: str) -> dict[str, str]:
    """The rendered element of every action id in an action space description (`I1[:]<input ...>`)."""
    lines: dict[str, str] = {}
    for line in description.splitlines():
        match = _DESCRIPTION_LINE.match(line.strip())
        if match is not None:
            _ = lines.setdefault(match.group(1), match.group(2).strip())
    return lines


def _cut(text: str, length: int) -> str:
    return text if len(text) <= length else text[:length] + "..."


def _role(action: InteractionAction, line: str) -> str:
    # checkboxes and radios get a B (button) or I (input) id depending on their markup
    if line.startswith("<input") and ('type="checkbox"' in line or 'type="radio"' in line):
        return "radio" if 'type="radio"' in line else "checkbox"
    match action.id[:1], action.type:
        case "L", _:
            return "link"
        case "B", _:
            return "button"
        case "F", _:
            return "image"
        case "O", _:
            return "option"
        case "I", "fill":
            return "textbox"
        case "I", "check":
            return "radio" if 'type="radio"' in line else "checkbox"
        case "I", "select_dropdown_option":
            return "select" if line.startswith("<select") else "combobox"
        case _:
            return "clickable"


def _element(
    action: InteractionAction,
    label: str,
    role: str,
    state: ElementState | None,
    has_live_state: bool,
    display_text: Callable[[str], str],
) -> dict[str, Any]:
    element: dict[str, Any] = {"index": action.id, "label": label, "role": role, "operations": []}
    if action.text_label and action.text_label not in label:
        element["text"] = _cut(display_text(action.text_label), 120)
    if state is not None:
        if state.value is not None:
            element["value"] = display_text(state.value)
        if state.filled is not None:
            element["filled"] = state.filled
        if state.checked is not None:
            element["checked"] = state.checked
        for key in ("expanded", "selected", "pressed"):
            value = getattr(state, key)
            if value is not None:
                element[key] = value
        if state.options is not None:
            element["value"] = display_text(", ".join(option.label for option in state.selected_options))
    elif has_live_state and role == "textbox":
        element["value"] = ""
    return element


def build_act_space(page: ObservedPage, *, display_text: Callable[[str], str] = str) -> ActSpace:
    # Determine IDs, roles and supported operations from the original page. Only
    # presentation strings pass through display_text, before their display caps.
    lines = description_lines(page.description)
    space = ActSpace()
    has_live_state = len(page.states) > 0

    def add(operation: Operation, target: Target, element: dict[str, Any]) -> None:
        _ = space.targets.setdefault(operation, {}).__setitem__(target.key, target)
        if operation not in element["operations"]:
            element["operations"].append(operation)

    for action in page.actions[:MAX_ELEMENTS]:
        if not action.id:
            continue
        line = lines.get(action.id, "")
        label = _cut(display_text(line or action.text_label or action.id), MAX_LABEL_LENGTH)
        role = _role(action, line)
        state = page.states.get(action.id)
        element = _element(action, label, role, state, has_live_state, display_text)
        current = element.get("value")
        base: dict[str, Any] = {k: element[k] for k in ("role", "checked", "selected", "expanded") if k in element}

        def target(kind: TargetKind, key: str | None = None, option: SelectOption | None = None) -> Target:
            key = key or action.id
            shown = label if option is None else f"{label} → {display_text(option.label)}"
            criteria = {"element": f"[{key}] {shown}", "current_value": current or "", **base}
            if option is not None:
                criteria["option_value"] = display_text(option.value)
            return Target(
                key=key,
                element_id=action.id,
                kind=kind,
                label=shown,
                criteria=criteria,
                option=option,
                checked=None if state is None else state.checked,
                role=role,
                value=current,
            )

        match role:
            case "textbox":
                add("TYPE_TEXT", target("fill"), element)
                add("CLICK", target("click"), element)
            case "combobox":
                editable = (
                    (line.startswith(("<input", "<textarea")) and "readonly" not in line)
                    or 'contenteditable="true"' in line
                    or 'contenteditable="plaintext-only"' in line
                )
                add("TYPE_TEXT", target("fill" if editable else "select_text"), element)
                add("CLICK", target("click"), element)
            case "checkbox" | "radio":
                add("CLICK", target("check"), element)
            case "select":
                options = None if state is None else state.options
                if options is None:
                    # no live state (remote session): the writer types the option label
                    add("TYPE_TEXT", target("select_text"), element)
                else:
                    listed: list[dict[str, str]] = []
                    element["options"] = listed
                    if state is not None and state.multiple:
                        # selecting an option replaces the current selection of a <select multiple>
                        element["multiple"] = True
                    for option in options:
                        if option.selected or option.disabled:
                            continue
                        key = f"{action.id}:{len(listed) + 1}"
                        listed.append(
                            {"index": key, "label": display_text(option.label), "value": display_text(option.value)}
                        )
                        add("SELECT", target("select_option", key, option), element)
                    if state is not None and state.options_truncated:
                        # long lists are cut (`ElementState.options`): the other options are typed by label
                        element["more_options"] = True
                        add("TYPE_TEXT", target("select_text"), element)
            case _:
                add("CLICK", target("click"), element)
        space.elements.append(element)

    viewport = page.viewport
    if viewport is None or viewport.scroll_y + viewport.viewport_height < viewport.total_height - 2:
        space.controls["SCROLL_DOWN"] = Control("SCROLL_DOWN", "Scroll down one page", ScrollDownAction())
    if viewport is None or viewport.scroll_y > 0:
        space.controls["SCROLL_UP"] = Control("SCROLL_UP", "Scroll up one page", ScrollUpAction())
    space.controls["PRESS_ENTER"] = Control(
        "PRESS_ENTER",
        "Press Enter in the focused field (e.g. submit a typed search that has no visible button)",
        PressKeyAction(key="Enter"),
    )
    space.controls["GO_BACK"] = Control("GO_BACK", "Go back to the previous page", GoBackAction())
    space.controls["WAIT"] = Control("WAIT", "Wait for the page to update", WaitAction(time_ms=WAIT_MS))
    return space


def page_state(page: ObservedPage) -> PageState:
    return PageState(url=page.url, title=page.title, text=_cut(page.description, MAX_PAGE_TEXT_LENGTH))


def act_questions(space: ActSpace, goal: str) -> dict[str, Question]:
    """The `operation` question and one target question per operation (jev-ultrafast's question set)."""
    questions = {
        "operation": Question(
            criteria=dict(space.operations), instructions={"goal": goal, "rules": prompts.NEXT_ACTION}
        )
    }
    for operation, candidates in space.targets.items():
        questions[_target_question(operation)] = Question(
            criteria={key: target.criteria for key, target in candidates.items()},
            instructions={"goal": goal, "operation": operation, "rules": [prompts.NEXT_ACTION, prompts.TARGET]},
        )
    return questions


def _target_question(operation: str) -> str:
    return operation.lower() + "_target"


def validate_answer(answers: Answers, question: str, keys: Mapping[str, Any]) -> Answer:
    """The answer to `question`, checked strictly: the choice is an offered option, there is a finite
    probability in [0, 1] for exactly the offered options, they sum to 1 and the choice is the most
    probable one. Raises `InvalidDecisionError` otherwise: nothing is executed on a malformed answer."""
    answer = answers.answers.get(question)
    if answer is None:
        raise InvalidDecisionError(f"no answer to question {question!r}")
    probabilities = answer.probabilities
    numbers = [*probabilities.values(), answer.confidence]
    valid = (
        answer.choice in keys
        and set(probabilities) == set(keys)
        and all(math.isfinite(n) and 0 <= n <= 1 for n in numbers)
        and abs(sum(probabilities.values()) - 1) < 0.02
        and probabilities[answer.choice] >= max(probabilities.values()) - 1e-6
    )
    if not valid:
        raise InvalidDecisionError(f"answer to {question!r} is not a valid choice among {len(keys)} options")
    return answer


@dataclass(frozen=True)
class Decision:
    operation: str
    operation_answer: Answer
    target: Target | None = None
    target_answer: Answer | None = None
    control: Control | None = None

    @property
    def confidence(self) -> float:
        if self.target_answer is None:
            return self.operation_answer.confidence
        return min(self.operation_answer.confidence, self.target_answer.confidence)

    @property
    def probabilities(self) -> dict[str, float]:
        if self.target_answer is not None:
            return dict(self.target_answer.probabilities)
        return dict(self.operation_answer.probabilities)


def interpret(answers: Answers, space: ActSpace) -> Decision:
    """Validate the operation answer, then only the target answer of the chosen operation."""
    operation_answer = validate_answer(answers, "operation", space.operations)
    operation = operation_answer.choice
    if operation in space.targets:
        candidates = space.targets[operation]
        target_answer = validate_answer(answers, _target_question(operation), candidates)
        return Decision(operation, operation_answer, candidates[target_answer.choice], target_answer)
    return Decision(operation, operation_answer, control=space.controls.get(operation))


def target_action(target: Target, text: str | None) -> InteractionAction:
    """The notte action for a chosen target. `text` is the (variable-substituted) value to type."""
    match target.kind:
        case "click":
            return ClickAction(id=target.element_id)
        case "check":
            if target.checked is None:
                return ClickAction(id=target.element_id)
            return CheckAction(id=target.element_id, value=not target.checked)
        case "fill":
            assert text is not None
            return FillAction(id=target.element_id, value=text)
        case "select_option":
            assert target.option is not None
            return SelectDropdownOptionAction(id=target.element_id, value=target.option.value)
        case "select_text":
            assert text is not None
            return SelectDropdownOptionAction(id=target.element_id, value=text)


def needs_text(target: Target) -> bool:
    return target.kind in ("fill", "select_text")


_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def substitute_variables(text: str, variables: Mapping[str, str]) -> str:
    """Replace every `{{name}}` of a known variable by its value (unknown names are left as they are)."""
    return _VARIABLE.sub(lambda match: variables.get(match.group(1), match.group(0)), text)
