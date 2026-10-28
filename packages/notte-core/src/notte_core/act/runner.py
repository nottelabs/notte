# The guards of `run_act` (freshness check right before acting, a decision used at most once, the
# written text reused when a stale page forces a new decision, the last 10 actions as history) are
# adapted from jev-ultrafast (`jev_ultrafast/agent.py`), Copyright (c) 2026 Browser Use, MIT License
# (see `LICENSE-jev-ultrafast`).
"""The `act()` / `choose()` / `check()` flow, independent of how a session is driven.

A session plugs in through an `ActDriver` (observe, re-check, execute); the decider answers.

`act(instruction)`:
1. observe the page (or use the given observation);
2. ask the decider the operation + target questions, validate the answers strictly;
3. DONE / BLOCKED / low confidence: return (BLOCKED raises `NoActionFoundError` by default);
4. TYPE_TEXT: ask the writer for the text, then substitute the caller's `{{variables}}`;
5. `dry_run`: return the action as `proposed`;
6. re-check the page: if the target changed since the observation, decide again once (reusing the
   written text for the same field), then give up with `stale`; the decision is never reused;
7. execute, and record the action in the session's history (last 10, sent as `recent_actions`), with the
   error class when it failed. A WAIT waits for the page to change, up to `WAIT_MS`.

An invalid answer (decision or field value) is asked again once; a second invalid answer blocks.
"""

import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

import notte_core.act.prompts as prompts
from notte_core.act.errors import InvalidDecisionError, NoActionFoundError
from notte_core.act.privacy import ActPrivacy
from notte_core.act.space import (
    WAIT_MS,
    ActSpace,
    Decision,
    LabelMode,
    ObservedPage,
    Target,
    accessible_names,
    act_questions,
    build_act_space,
    changed_beyond,
    field_context,
    find_field,
    interpret,
    label_mode,
    needs_text,
    page_state,
    page_text,
    substitute_variables,
    target_action,
    validate_answer,
)
from notte_core.act.types import (
    ActResult,
    ActTimings,
    Answer,
    Answers,
    Choice,
    Decider,
    DecisionState,
    PageState,
    Question,
    WriteContext,
)
from notte_core.actions import BaseAction, CheckAction, FillAction
from notte_core.credentials.base import (
    CardCVVField,
    CardFullExpirationField,
    CardHolderField,
    CardNumberField,
    CredentialField,
    EmailField,
    MFAField,
    PasswordField,
    UserNameField,
)
from notte_core.dom_tree import NodeSelectors
from notte_core.errors import ContentFilterError, FileChooserOpenedError
from notte_core.observation import ExecutionResult, Observation

HISTORY_SIZE = 10
WRITER_HISTORY_SIZE = 6
WRITER_PAGE_TEXT_LENGTH = 6_000
# the other fields with a value sent to the writer (`page.fields`), the closest to the target
WRITER_FIELDS = 12
# the elements right after the target sent to the writer (`page.next_controls`)
WRITER_NEXT_CONTROLS = 4
# the `error` of a history entry for a field the writer had no value for (nothing was typed)
NO_VALUE = "NoValueFromInstruction"


class ActDriver(Protocol):
    """How `run_act` reads and drives one session."""

    @property
    def has_vault(self) -> bool:
        """A vault is attached: credential fields get vault placeholders, swapped for secrets at execution."""
        ...

    def secret_replacements(self) -> Mapping[str, str]:
        """Credential values the vault already typed in this session, mapped to their placeholders: they are
        masked in every model request (the live state reads field values back)."""
        ...

    async def observe(self, observation: Observation | None) -> ObservedPage:
        """Observe the page (or wrap `observation`, already taken on the current page), and record
        what `is_fresh` will compare against."""
        ...

    async def is_fresh(self, page: ObservedPage, element_id: str | None, *, focus: bool = False) -> bool:
        """Right before acting: the page still matches `page` (same URL and, for an element target,
        the same element under the same id; with `focus`, the same focused element). As cheap as the
        session allows."""
        ...

    async def execute(self, action: BaseAction, raise_on_failure: bool) -> ExecutionResult: ...

    async def wait_for_change(self, timeout_ms: int, raise_on_failure: bool) -> ExecutionResult:
        """Wait until the page changes (DOM change or navigation), at most `timeout_ms` (`notte_core.act.wait`).
        A failed wait raises, like `execute`, with `raise_on_failure`."""
        ...


@dataclass
class TypedText:
    """Text a TYPE_TEXT put in a field, while nothing submitted it (see `ActHistory`)."""

    # the field's accessible name and the text typed (variables substituted): how the field is found again
    name: str
    value: str
    url: str
    # the page typed on, until the next observation tells whether typing alone changed the page (a live filter)
    before: ObservedPage | None
    # the field's id on the page typed on, then on the last observed page
    element_id: str
    selectors: NodeSelectors | None = None


@dataclass
class ActHistoryEntry:
    action: str
    kind: str
    text: str | None
    fingerprint: str
    page_changed: bool | None = None
    # filled in by the next observation; False when it cannot be known (see `ActHistory`)
    pending: bool = True
    # the error class of a failed execution (never its message: it can quote page content or values)
    error: str | None = None
    # a TYPE_TEXT whose text is not submitted yet
    typed: TypedText | None = None
    # The page read before this action, exposed in history only after leaving it.
    page: PageState | None = None
    left_page: bool = False
    # raw URL used only to detect navigation; `page` is masked for model requests
    source_url: str | None = field(default=None, repr=False)


# clicking these does not submit what was typed in a field
_FORM_ROLES = ("textbox", "combobox", "checkbox", "radio", "select")


@dataclass
class ActHistory:
    """The last `act()` actions of a session, sent to the decider as `recent_actions`.

    `page_changed` is filled in by the next observation (comparing page fingerprints), so it costs no
    extra observation. A fill on a driver without live state leaves it unknown.

    Text typed in a field is `submitted: false` (in the history and on the field) while nothing submitted it: no
    PRESS_ENTER, GO_BACK or click on anything but a form field since, the URL is the same and the field still holds
    the text. A field that applies its text as it is typed (a live filter changing the URL or the page) is not.
    """

    entries: deque[ActHistoryEntry] = field(default_factory=lambda: deque(maxlen=HISTORY_SIZE))
    privacy: ActPrivacy = field(default_factory=ActPrivacy, repr=False)

    def observed(self, page: ObservedPage) -> None:
        if len(self.entries) > 0 and self.entries[-1].pending:
            self.entries[-1].page_changed = page.fingerprint != self.entries[-1].fingerprint
            self.entries[-1].pending = False
            source_url = self.entries[-1].source_url
            self.entries[-1].left_page = source_url is not None and source_url != page.url
        for entry in self.entries:
            if entry.typed is not None:
                entry.typed = _still_typed(entry.typed, page)

    def acted(self, operation: str, target: Target | None) -> None:
        """After `operation` ran successfully: one that can submit typed text ends the tracking of every typed field."""
        click = operation in ("CLICK", "CLOSE_DIALOG") and (target is None or target.role not in _FORM_ROLES)
        if click or operation in ("PRESS_ENTER", "GO_BACK"):
            for entry in self.entries:
                entry.typed = None

    def typed(self, typed: TypedText) -> None:
        """`typed` was just typed: it replaces what was typed earlier in the same field."""
        for entry in self.entries:
            previous = entry.typed
            if previous is None or previous.url != typed.url:
                continue
            same = (
                previous.selectors == typed.selectors
                if typed.selectors is not None
                else (previous.element_id, previous.name) == (typed.element_id, typed.name)
            )
            if same:
                entry.typed = None

    def acted_since_observed(self) -> bool:
        """An action other than a WAIT ran since the last observation (the next one tells what it changed)."""
        return len(self.entries) > 0 and self.entries[-1].pending and self.entries[-1].kind != "WAIT"

    def unsubmitted(self) -> set[str]:
        """The ids, on the last observed page, of the fields holding typed text not submitted yet."""
        return {e.typed.element_id for e in self.entries if e.typed is not None and e.typed.before is None}

    def recent(self, limit: int = HISTORY_SIZE) -> list[dict[str, Any]]:
        # The page an action left is `previous_page`: under `page`, deciders read it as the page the action led to
        # and doubt the current one (a goal page opened by a click looked unopened).
        return [
            {"action": e.action, "kind": e.kind, "text": e.text, "page_changed": e.page_changed}
            | ({} if e.error is None else {"error": e.error})
            | ({} if e.typed is None or e.typed.before is not None else {"submitted": False})
            | ({} if not e.left_page or e.page is None else {"previous_page": e.page.model_dump()})
            for e in list(self.entries)[-limit:]
        ]


def _still_typed(typed: TypedText, page: ObservedPage) -> TypedText | None:
    """`typed` on the newly observed `page`, or None once it is submitted or applied: the URL changed, the field no
    longer holds the text, or (on the first observation after typing) typing changed the page beyond the field."""
    if page.url != typed.url:
        return None
    element_id = find_field(page, typed.name, typed.value, selectors=typed.selectors)
    if element_id is None:
        return None
    if typed.before is not None:
        before = typed.before.states.get(typed.element_id)
        values = [typed.value, "" if before is None or before.value is None else before.value]
        if changed_beyond(typed.before, page, typed.element_id, values):
            return None
    return replace(typed, before=None, element_id=element_id)


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


# the vault placeholders the field writer answers for credential fields, by field kind
_CREDENTIAL_FIELDS: dict[str, type[CredentialField]] = {
    "an email": EmailField,
    "a username": UserNameField,
    "a password": PasswordField,
    "a 2FA code": MFAField,
    "a card holder name": CardHolderField,
    "a card number": CardNumberField,
    "a card CVV": CardCVVField,
    "a card expiration date": CardFullExpirationField,
}


def _credentials(has_vault: bool) -> list[str]:
    if not has_vault:
        return []
    return [
        f"To fill in {kind}, use the value '{field.placeholder_value}'" for kind, field in _CREDENTIAL_FIELDS.items()
    ]


@dataclass
class _Run:
    instruction: str
    started: float = field(default_factory=time.perf_counter)
    timings: ActTimings = field(default_factory=ActTimings)
    model: str | None = None

    def result(self, **fields: Any) -> ActResult:
        self.timings.total_ms = _ms(self.started)
        return ActResult(instruction=self.instruction, model=self.model, timings=self.timings, **fields)


async def run_act(
    driver: ActDriver,
    decider: Decider,
    history: ActHistory,
    instruction: str,
    *,
    variables: Mapping[str, str] | None = None,
    dry_run: bool = False,
    min_confidence: float = 0.0,
    observation: Observation | None = None,
    raise_on_failure: bool = True,
) -> ActResult:
    run = _Run(instruction=instruction)
    variables = dict(variables or {})
    history.privacy.remember(variables)
    labels = label_mode()
    # text written for a field, reused if a stale page forces a new decision on the same field (`_field_identity`)
    written: dict[tuple[str, ...], str] = {}
    # the fields the writer had no value for, not offered to TYPE_TEXT when deciding again
    no_text: set[tuple[str, str]] = set()

    for attempt in range(2):
        step = time.perf_counter()
        page = await driver.observe(observation if attempt == 0 else None)
        run.timings.observe_ms += _ms(step)
        history.observed(page)
        history.privacy.remember_secrets(driver.secret_replacements())

        space = build_act_space(
            page,
            display_text=history.privacy.text,
            labels=labels,
            display_cut=history.privacy.cut_text,
            no_text=no_text,
            unsubmitted=history.unsubmitted(),
        )
        model_page = history.privacy.page(page)
        state = DecisionState(
            page=page_state(model_page, labels, history.privacy.text, viewport_only=True),
            elements=space.elements,
            recent_actions=history.privacy.payload(history.recent()),
        )
        step = time.perf_counter()
        questions = act_questions(space, history.privacy.text(instruction))
        try:
            decision = await _decide(decider, state, questions, space, run)
        except InvalidDecisionError as e:
            run.timings.decide_ms += _ms(step)
            return _invalid(run, e, raise_on_failure, page.fingerprint)
        run.timings.decide_ms += _ms(step)
        common: dict[str, Any] = dict(
            fingerprint=page.fingerprint,
            operation=decision.operation,
            target=None if decision.target is None else decision.target.key,
            confidence=decision.confidence,
            probabilities=decision.probabilities,
            operation_probabilities=dict(decision.operation_answer.probabilities),
        )

        if decision.operation == "DONE":
            return run.result(status="done", message="The decider found the instruction satisfied.", **common)
        if decision.operation == "BLOCKED" or decision.confidence < min_confidence:
            reason = (
                "the decider found no operation that can make progress"
                if decision.operation == "BLOCKED"
                else f"confidence {decision.confidence:.2f} is below min_confidence={min_confidence}"
            )
            if space.file_input:
                reason += f" ({prompts.FILE_UPLOAD_UNSUPPORTED})"
            return _blocked(run, reason, raise_on_failure, common)

        target = decision.target
        text: str | None = None
        if target is not None and needs_text(target):
            key = _field_identity(page, target)
            text = written.get(key)
            if text is None:
                step = time.perf_counter()
                context = _write_context(instruction, target, space, model_page, history, variables, driver, labels)
                try:
                    text = await _write(decider, context)
                except ContentFilterError as e:
                    run.timings.write_ms += _ms(step)
                    return _blocked(run, f"the field writer refused: {e.dev_message}", raise_on_failure, common, e)
                except InvalidDecisionError as e:
                    run.timings.write_ms += _ms(step)
                    return _invalid(run, e, raise_on_failure, page.fingerprint, common)
                run.timings.write_ms += _ms(step)
                # "" clears a field, but names no option of a dropdown and clears nothing in an empty field
                empty = not target.value and not target.filled
                if text is None or (text == "" and (target.kind == "select_text" or empty)):
                    if attempt == 0:
                        # the field is not the next step (a vague label, a field the goal does not mention):
                        # decide again without it, the decider told through the history
                        no_text.add((target.element_id, target.label))
                        history.entries.append(
                            ActHistoryEntry(
                                action=target.label,
                                kind="TYPE_TEXT",
                                text=None,
                                fingerprint=page.fingerprint,
                                page_changed=False,
                                pending=False,
                                error=NO_VALUE,
                            )
                        )
                        continue
                    return _blocked(
                        run, f"no value to type in {target.label!r} from the instruction", raise_on_failure, common
                    )
                written[key] = text
        common["value"] = text

        if target is not None:
            action: BaseAction = target_action(target, None if text is None else substitute_variables(text, variables))
            # which of two same-named elements ran ("Add to cart" of the product, not of the accessory)
            label = target.label if target.context is None else f"{target.label} (in: {target.context})"
            if isinstance(action, CheckAction):
                # "CLICK <checkbox>" alone reads as checking it: say which way it went
                label = f"{'Check' if action.value else 'Uncheck'} {label}"
        else:
            assert decision.control is not None
            action = decision.control.action.model_copy()
            label = decision.control.label

        if dry_run:
            return run.result(status="proposed", action=action, **common)

        step = time.perf_counter()
        # Enter goes to the focused element: it must still be the one the decision saw
        fresh = await driver.is_fresh(
            page, None if target is None else target.element_id, focus=decision.operation == "PRESS_ENTER"
        )
        run.timings.fresh_ms += _ms(step)
        if not fresh:
            if attempt == 0:
                continue
            return run.result(
                status="stale", message="The page kept changing between decision and execution.", **common
            )

        # without live state a typed value does not change the fingerprint
        unknown = decision.operation == "TYPE_TEXT" and len(page.states) == 0
        entry = ActHistoryEntry(
            action=label,
            kind=decision.operation,
            text=text,
            fingerprint=page.fingerprint,
            pending=not unknown,
            page=state.page,
            source_url=page.url,
        )
        step = time.perf_counter()
        try:
            if decision.operation == "WAIT":
                execution = await driver.wait_for_change(WAIT_MS, raise_on_failure)
            else:
                execution = await driver.execute(action, raise_on_failure)
        except Exception as e:
            entry.error = type(e).__name__
            history.entries.append(entry)
            if isinstance(e, FileChooserOpenedError):
                return _blocked(run, _FILE_CHOOSER_OPENED, raise_on_failure, common, e)
            raise
        run.timings.execute_ms += _ms(step)
        if not execution.success:
            entry.error = "ExecutionFailed" if execution.exception is None else type(execution.exception).__name__
            if isinstance(execution.exception, FileChooserOpenedError):
                # the page asks for a file, which act cannot give: clicking again would open the chooser again
                history.entries.append(entry)
                return _blocked(run, _FILE_CHOOSER_OPENED, raise_on_failure, common, execution.exception)
        else:
            # a submit that failed (or raised) submitted nothing: the typed text stays unsubmitted
            history.acted(decision.operation, target)
        if unknown:
            # The loop must not mistake unobservable fills for lack of progress.
            common["fingerprint"] = None
        elif isinstance(action, FillAction) and isinstance(action.value, str) and action.value and execution.success:
            assert target is not None
            entry.typed = _typed(page, target.element_id, action.value)
            if entry.typed is not None:
                history.typed(entry.typed)
        history.entries.append(entry)
        return run.result(status="executed", action=action, execution=execution, message=execution.message, **common)

    raise AssertionError("unreachable")  # pragma: no cover


def _typed(page: ObservedPage, element_id: str, value: str) -> TypedText | None:
    """What was typed in the field `element_id` of `page`, to tell later whether it was submitted (None for a field
    without a name, which cannot be found again)."""
    name = accessible_names(page).get(element_id)
    if not name:
        return None
    action = next(action for action in page.actions if action.id == element_id)
    return TypedText(
        name=name, value=value, url=page.url, before=page, element_id=element_id, selectors=action.selectors
    )


async def _decide(
    decider: Decider, state: DecisionState, questions: dict[str, Question], space: ActSpace, run: _Run
) -> Decision:
    """The decision, asked again once if the answer is invalid (raises the second `InvalidDecisionError`)."""
    for attempt in range(2):
        try:
            answers = await decider.choose(state, questions)
            run.model = answers.model
            return interpret(answers, space)
        except InvalidDecisionError:
            if attempt == 1:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


async def _answer(
    decider: Decider, state: DecisionState, questions: dict[str, Question], keys: Mapping[str, Any]
) -> tuple[Answers, Answer]:
    """The answer to a page question, asked again once if it is invalid (raises the second `InvalidDecisionError`)."""
    for attempt in range(2):
        answers = await decider.choose(state, questions)
        try:
            return answers, validate_answer(answers, "answer", keys)
        except InvalidDecisionError:
            if attempt == 1:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


def _field_identity(page: ObservedPage, target: Target) -> tuple[str, ...]:
    """Which field written text belongs to. Ids and XPaths are positions: once the page re-rendered, the same id can be
    another field with the same label (a shipping "Name" where the billing one was), told apart by its section
    context and selectors (with their iframe and shadow-root path)."""
    selectors = next((action.selectors for action in page.actions if action.id == target.element_id), None)
    return (
        target.element_id,
        target.label,
        target.context or "",
        "" if selectors is None else selectors.model_dump_json(),
        page.url,
    )


async def _write(decider: Decider, context: WriteContext) -> str | None:
    """The field value, asked again once if the writer's answer is invalid."""
    try:
        return await decider.write(context)
    except InvalidDecisionError:
        return await decider.write(context)


def _invalid(
    run: _Run,
    error: InvalidDecisionError,
    raise_on_failure: bool,
    fingerprint: str,
    common: dict[str, Any] | None = None,
) -> ActResult:
    """Two invalid answers in a row: nothing ran. Raises `error` unless `raise_on_failure=False`."""
    if raise_on_failure:
        raise error
    fields = common if common is not None else {"fingerprint": fingerprint}
    return run.result(status="blocked", message=f"the decider answered invalidly twice: {error.dev_message}", **fields)


_FILE_CHOOSER_OPENED = f"the click opened a file chooser ({prompts.FILE_UPLOAD_UNSUPPORTED})"


def _blocked(
    run: _Run, reason: str, raise_on_failure: bool, common: dict[str, Any], cause: Exception | None = None
) -> ActResult:
    result = run.result(status="blocked", message=reason, **common)
    if raise_on_failure:
        raise NoActionFoundError(run.instruction, reason, result) from cause
    return result


def same_target(page: ObservedPage, current: ObservedPage, element_id: str | None) -> bool:
    """`current` (a new observation) still matches the decision taken on `page`: same URL and, for an
    element target, the same element (type, label, selector, live state) under the same id."""
    if current.url != page.url:
        return False
    if element_id is None:
        return True
    before = page.signature(element_id)
    return before is not None and current.signature(element_id) == before


def _write_context(
    instruction: str,
    target: Target,
    space: ActSpace,
    page: ObservedPage,
    history: ActHistory,
    variables: Mapping[str, str],
    driver: ActDriver,
    labels: LabelMode,
) -> WriteContext:
    """The field (with its id, as in the page text's `[I1]` markers, and its placeholder and the text before it
    when they say more than its label), the page text around it, and the values of the other fields: a short or
    vague label ("Departure") is read with the rest of the form."""
    field: dict[str, Any] = {
        "index": target.element_id,
        "label": target.label,
        "role": target.role,
        "value": target.value or "",
    }
    field.update(field_context(page, target.element_id, labels, history.privacy.text, exclude=target.label))
    if target.input_type is not None:
        field["type"] = target.input_type
    if target.value_format is not None:
        field["format"] = target.value_format
    if target.context is not None:
        field["context"] = target.context
    text = page_text(page, labels, history.privacy.text, WRITER_PAGE_TEXT_LENGTH, focus=target.element_id)
    return WriteContext(
        goal=history.privacy.text(instruction),
        field=field,
        page={
            "title": page.title,
            "text": text,
            "fields": _other_fields(space, target.element_id),
            "next_controls": _next_controls(space, target.element_id),
        },
        recent_actions=history.privacy.payload(
            [
                {"action": e["action"], "text": e["text"]}
                | ({} if "previous_page" not in e else {"previous_page": e["previous_page"]})
                for e in history.recent(WRITER_HISTORY_SIZE)
            ]
        ),
        variables=sorted(variables),
        credentials=_credentials(driver.has_vault),
    )


def _next_controls(space: ActSpace, element_id: str) -> list[str]:
    """The labels of the elements right after the target (`WRITER_NEXT_CONTROLS`): the form's other controls (a
    date picker, a guests selector) take their part of the goal, not a free-text field before them."""
    position = next((i for i, e in enumerate(space.elements) if e["index"] == element_id), len(space.elements))
    return [e["label"] for e in space.elements[position + 1 : position + 1 + WRITER_NEXT_CONTROLS]]


def _other_fields(space: ActSpace, element_id: str) -> list[dict[str, str]]:
    """The other fields of the page that hold a value (label and value), the `WRITER_FIELDS` closest to the target."""
    fields = [e for e in space.elements if e.get("role") in ("textbox", "combobox", "select")]
    position = next((i for i, e in enumerate(fields) if e["index"] == element_id), 0)
    filled = [(i, e) for i, e in enumerate(fields) if e["index"] != element_id and e.get("value")]
    closest = sorted(filled, key=lambda pair: abs(pair[0] - position))[:WRITER_FIELDS]
    return [
        {"index": e["index"], "label": e["label"], "value": e["value"]} for _, e in sorted(closest, key=lambda p: p[0])
    ]


async def run_choose(
    driver: ActDriver,
    decider: Decider,
    history: ActHistory,
    question: str,
    options: Sequence[str] | Mapping[str, str],
    *,
    observation: Observation | None = None,
    rules: str = prompts.CHOOSE,
) -> Choice:
    """Ask the decider to pick one of `options` about the current page."""
    criteria: dict[str, Any] = dict(options) if isinstance(options, Mapping) else {o: o for o in options}
    if len(criteria) < 2:
        raise ValueError("choose() needs at least two options")
    labels = label_mode()
    page = await driver.observe(observation)
    history.observed(page)
    history.privacy.remember_secrets(driver.secret_replacements())
    model_page = history.privacy.page(page)
    state = DecisionState(
        page=page_state(model_page, labels, history.privacy.text),
        elements=build_act_space(
            page, display_text=history.privacy.text, labels=labels, display_cut=history.privacy.cut_text
        ).elements,
        recent_actions=history.privacy.payload(history.recent()),
    )
    # Option keys reach the model too: send them masked and map the answer back.
    keys = _model_keys(list(criteria), history.privacy.text)
    sent = {keys[option]: description for option, description in criteria.items()}
    questions = {
        "answer": Question(
            criteria=history.privacy.payload(sent),
            instructions=history.privacy.payload({"goal": question, "rules": rules}),
        )
    }
    answers, answer = await _answer(decider, state, questions, sent)
    option = {key: option for option, key in keys.items()}
    return Choice(
        choice=option[answer.choice],
        probabilities={option[key]: p for key, p in answer.probabilities.items()},
        confidence=answer.confidence,
        model=answers.model,
    )


def _model_keys(options: list[str], mask: Callable[[str], str]) -> dict[str, str]:
    """Each option's key in the model request: masked, or numbered when masking makes two keys equal."""
    masked = [mask(option) for option in options]
    if len(set(masked)) == len(masked):
        return dict(zip(options, masked))
    return {option: f"option {i}" for i, option in enumerate(options, 1)}


CHECK_OPTIONS = {
    "YES": "Yes: the statement holds / the answer is yes for the current page.",
    "NO": "No: the statement does not hold / the answer is no for the current page.",
}


async def run_check(
    driver: ActDriver,
    decider: Decider,
    history: ActHistory,
    question: str,
    *,
    observation: Observation | None = None,
) -> float:
    """The probability that `question` holds on the current page."""
    choice = await run_choose(
        driver, decider, history, question, CHECK_OPTIONS, observation=observation, rules=prompts.CHECK
    )
    return choice.probabilities["YES"]
