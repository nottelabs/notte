# The guards of `run_act` (freshness check right before acting, a decision used at most once, the
# written text reused when a stale page forces a new decision, the last 10 actions as history) are
# adapted from jev-ultrafast (`jev_ultrafast/agent.py`), Copyright (c) 2026 Browser Use, MIT License
# (see `LICENSE-jev-ultrafast`).
"""The `act()` / `choose()` / `check()` flow, shared by local and remote sessions.

A session plugs in through an `ActDriver` (observe, re-check, execute); the decider answers.

`act(instruction)`:
1. observe the page (or use the given observation);
2. ask the decider the operation + target questions, validate the answers strictly;
3. DONE / BLOCKED / low confidence: return (BLOCKED raises `NoActionFoundError` by default);
4. TYPE_TEXT: ask the writer for the text, then substitute the caller's `{{variables}}`;
5. `dry_run`: return the action as `proposed`;
6. re-check the page: if the target changed since the observation, decide again once (reusing the
   written text for the same field), then give up with `stale`; the decision is never reused;
7. execute, and record the action in the session's history (last 10, sent as `recent_actions`).
"""

import time
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import notte_core.act.prompts as prompts
from notte_core.act.errors import NoActionFoundError
from notte_core.act.privacy import ActPrivacy
from notte_core.act.space import (
    LabelMode,
    ObservedPage,
    Target,
    act_questions,
    build_act_space,
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
    Choice,
    Decider,
    DecisionState,
    Question,
    WriteContext,
)
from notte_core.actions import BaseAction, CheckAction
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
from notte_core.errors import ContentFilterError
from notte_core.observation import ExecutionResult, Observation

HISTORY_SIZE = 10
WRITER_HISTORY_SIZE = 6
WRITER_PAGE_TEXT_LENGTH = 6_000


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

    async def is_fresh(self, page: ObservedPage, element_id: str | None) -> bool:
        """Right before acting: the page still matches `page` (same URL and, for an element target,
        the same element under the same id). As cheap as the session allows."""
        ...

    async def execute(self, action: BaseAction, raise_on_failure: bool) -> ExecutionResult: ...


@dataclass
class ActHistoryEntry:
    action: str
    kind: str
    text: str | None
    fingerprint: str
    page_changed: bool | None = None
    # filled in by the next observation; False when it cannot be known (see `ActHistory`)
    pending: bool = True


@dataclass
class ActHistory:
    """The last `act()` actions of a session, sent to the decider as `recent_actions`.

    `page_changed` is filled in by the next observation (comparing page fingerprints), so it costs no
    extra observation. A fill without live state (remote sessions) leaves it unknown.
    """

    entries: deque[ActHistoryEntry] = field(default_factory=lambda: deque(maxlen=HISTORY_SIZE))
    privacy: ActPrivacy = field(default_factory=ActPrivacy, repr=False)

    def observed(self, fingerprint: str) -> None:
        if len(self.entries) > 0 and self.entries[-1].pending:
            self.entries[-1].page_changed = fingerprint != self.entries[-1].fingerprint
            self.entries[-1].pending = False

    def recent(self, limit: int = HISTORY_SIZE) -> list[dict[str, Any]]:
        return [
            {"action": e.action, "kind": e.kind, "text": e.text, "page_changed": e.page_changed}
            for e in list(self.entries)[-limit:]
        ]


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
    # text written for a field, reused if a stale page forces a new decision on the same field
    written: dict[tuple[str, str, str], str] = {}

    for attempt in range(2):
        step = time.perf_counter()
        page = await driver.observe(observation if attempt == 0 else None)
        run.timings.observe_ms += _ms(step)
        history.observed(page.fingerprint)
        history.privacy.remember_secrets(driver.secret_replacements())

        space = build_act_space(
            page, display_text=history.privacy.text, labels=labels, display_cut=history.privacy.cut_text
        )
        model_page = history.privacy.page(page)
        state = DecisionState(
            page=page_state(model_page, labels, history.privacy.text),
            elements=space.elements,
            recent_actions=history.privacy.payload(history.recent()),
        )
        step = time.perf_counter()
        questions = act_questions(space, history.privacy.text(instruction))
        answers = await decider.choose(state, questions)
        run.timings.decide_ms += _ms(step)
        run.model = answers.model
        decision = interpret(answers, space)
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
            return _blocked(run, reason, raise_on_failure, common)

        target = decision.target
        text: str | None = None
        if target is not None and needs_text(target):
            key = (target.element_id, target.label, page.url)
            text = written.get(key)
            if text is None:
                step = time.perf_counter()
                context = _write_context(instruction, target, model_page, history, variables, driver, labels)
                try:
                    text = await decider.write(context)
                except ContentFilterError as e:
                    run.timings.write_ms += _ms(step)
                    return _blocked(run, f"the field writer refused: {e.dev_message}", raise_on_failure, common, e)
                run.timings.write_ms += _ms(step)
                # "" clears a field, but names no option of a dropdown
                if text is None or (text == "" and target.kind == "select_text"):
                    return _blocked(
                        run, f"no value to type in {target.label!r} from the instruction", raise_on_failure, common
                    )
                written[key] = text
        common["value"] = text

        if target is not None:
            action: BaseAction = target_action(target, None if text is None else substitute_variables(text, variables))
            label = target.label
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
        fresh = await driver.is_fresh(page, None if target is None else target.element_id)
        run.timings.fresh_ms += _ms(step)
        if not fresh:
            if attempt == 0:
                continue
            return run.result(
                status="stale", message="The page kept changing between decision and execution.", **common
            )

        step = time.perf_counter()
        execution = await driver.execute(action, raise_on_failure)
        run.timings.execute_ms += _ms(step)
        # without live state (remote sessions) a typed value does not change the fingerprint
        unknown = decision.operation == "TYPE_TEXT" and len(page.states) == 0
        if unknown:
            # The loop must not mistake unobservable cloud fills for lack of progress.
            common["fingerprint"] = None
        history.entries.append(
            ActHistoryEntry(
                action=label, kind=decision.operation, text=text, fingerprint=page.fingerprint, pending=not unknown
            )
        )
        return run.result(status="executed", action=action, execution=execution, message=execution.message, **common)

    raise AssertionError("unreachable")  # pragma: no cover


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
    page: ObservedPage,
    history: ActHistory,
    variables: Mapping[str, str],
    driver: ActDriver,
    labels: LabelMode,
) -> WriteContext:
    field: dict[str, Any] = {"label": target.label, "role": target.role, "value": target.value or ""}
    text = page_text(page, labels, history.privacy.text)
    return WriteContext(
        goal=history.privacy.text(instruction),
        field=field,
        page={"title": page.title, "text": text[:WRITER_PAGE_TEXT_LENGTH]},
        recent_actions=history.privacy.payload(
            [{"action": e["action"], "text": e["text"]} for e in history.recent(WRITER_HISTORY_SIZE)]
        ),
        variables=sorted(variables),
        credentials=_credentials(driver.has_vault),
    )


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
    history.observed(page.fingerprint)
    history.privacy.remember_secrets(driver.secret_replacements())
    model_page = history.privacy.page(page)
    state = DecisionState(
        page=page_state(model_page, labels, history.privacy.text),
        elements=build_act_space(
            page, display_text=history.privacy.text, labels=labels, display_cut=history.privacy.cut_text
        ).elements,
        recent_actions=history.privacy.payload(history.recent()),
    )
    questions = {
        "answer": Question(
            criteria=history.privacy.payload(criteria),
            instructions=history.privacy.payload({"goal": question, "rules": rules}),
        )
    }
    answers = await decider.choose(state, questions)
    answer = validate_answer(answers, "answer", criteria)
    return Choice(
        choice=answer.choice, probabilities=answer.probabilities, confidence=answer.confidence, model=answers.model
    )


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
