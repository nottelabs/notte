"""Types shared by `session.act()` / `choose()` / `check()` and the deciders that answer them.

A decider answers typed multiple-choice questions about a page (`Decider.choose`) and writes field
values (`Decider.write`). It never sees selectors or produces actions: notte builds the questions
from the observed page and maps the chosen option back to a notte action.
"""

from collections.abc import Mapping
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from notte_core.actions import BaseAction
from notte_core.observation import ExecutionResult


class Question(BaseModel):
    """A multiple-choice question: `criteria` maps each option key to what the option means."""

    type: Literal["choice"] = "choice"
    criteria: dict[str, Any]
    instructions: dict[str, Any] = Field(default_factory=dict)


class Answer(BaseModel):
    """The answer to one question: the chosen option key, a probability per option, and a confidence."""

    choice: str
    probabilities: dict[str, float]
    confidence: float


class Answers(BaseModel):
    """The answers of one `Decider.choose` call, by question name."""

    answers: dict[str, Answer]
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)


class PageState(BaseModel):
    url: str
    title: str
    # the rendered page: interactive elements (`B1[:]<button>...`) and text (`_[:]...`), untrusted
    text: str


class DecisionState(BaseModel):
    """What the decider sees: the page, its interactive elements and the recent `act()` results."""

    page: PageState
    elements: list[dict[str, Any]] = Field(default_factory=list)
    recent_actions: list[dict[str, Any]] = Field(default_factory=list)


class WriteContext(BaseModel):
    """What the field writer sees to produce the text of one field.

    `variables` are the names of the caller's variables: the writer answers `{{name}}` and notte
    substitutes the value after the call, so values never reach the model. `credentials` lists the
    vault placeholders to use for credential fields (the vault swaps them for the secrets at execution).
    """

    goal: str
    field: dict[str, Any]
    page: dict[str, Any]
    recent_actions: list[dict[str, Any]] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    credentials: list[str] = Field(default_factory=list)


@runtime_checkable
class Decider(Protocol):
    """Answers the questions of `act()` / `choose()` / `check()` and writes field values.

    Implementations: `notte_llm.JevDecider` (TypeSafe's Jev classification model) and
    `notte_llm.LlmDecider` (an LLM of the `NOTTE_LLM_*` endpoint). Any object with these two methods works.
    """

    async def choose(self, state: DecisionState, questions: Mapping[str, Question]) -> Answers:
        """Answer every question (option keys must come from each question's `criteria`)."""
        ...

    async def write(self, context: WriteContext) -> str | None:
        """The exact text to type in a field, or `None` when the goal does not give a value."""
        ...


ActStatus = Literal["executed", "proposed", "done", "blocked", "stale"]


class ActTimings(BaseModel):
    """Milliseconds spent in each step of one `act()` call (summed over a stale retry)."""

    observe_ms: float = 0.0
    decide_ms: float = 0.0
    write_ms: float = 0.0
    fresh_ms: float = 0.0
    execute_ms: float = 0.0
    total_ms: float = 0.0


class ActResult(BaseModel):
    """The outcome of `session.act(instruction)`.

    - `executed`: `action` ran; `execution` holds its result (check `execution.success`).
    - `proposed`: `dry_run=True`; `action` was chosen but not run (`session.execute(result.action)` runs it).
    - `done`: the decider found the instruction already satisfied on the page; nothing ran.
    - `blocked`: no operation can progress (decider answered BLOCKED, confidence below
      `min_confidence`, or no field value); raises `NoActionFoundError` unless `raise_on_failure=False`.
    - `stale`: the page changed between the decision and the execution, twice; nothing ran.
    """

    instruction: str
    status: ActStatus
    action: BaseAction | None = None
    execution: ExecutionResult | None = None
    # operation chosen: CLICK, TYPE_TEXT, SELECT, a control (SCROLL_DOWN, WAIT, ...), DONE or BLOCKED
    operation: str | None = None
    # element id (`B1`), or `<id>:<n>` for the n-th option of a select
    target: str | None = None
    # text typed in the field as written by the model: variables stay as `{{name}}`
    value: str | None = None
    # lowest of the operation and target confidences
    confidence: float | None = None
    # probabilities of the target options (or of the operations when there is no target)
    probabilities: dict[str, float] = Field(default_factory=dict)
    operation_probabilities: dict[str, float] = Field(default_factory=dict)
    model: str | None = None
    message: str | None = None
    # fingerprint of the decision page; None for fills whose changes cannot be observed (no live state)
    fingerprint: str | None = None
    timings: ActTimings = Field(default_factory=ActTimings)

    @property
    def success(self) -> bool:
        """The instruction was carried out (or already satisfied, or proposed with `dry_run`)."""
        if self.status == "executed":
            return self.execution is not None and self.execution.success
        return self.status in ("done", "proposed")


class Choice(BaseModel):
    """The answer of `session.choose(question, options)`."""

    choice: str
    probabilities: dict[str, float]
    confidence: float
    model: str | None = None
