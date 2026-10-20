"""Errors of `session.act()` / `choose()` / `check()`."""

from typing import TYPE_CHECKING

from notte_core.errors import NotteBaseError

if TYPE_CHECKING:
    from notte_core.act.types import ActResult


class ActError(NotteBaseError):
    """Base class for `session.act()` / `choose()` / `check()` errors."""

    pass


class DeciderNotAvailableError(ActError):
    """No decider could be resolved for `act()`: no TypeSafe key, no LLM configured, or `notte-llm` missing."""

    def __init__(self, reason: str | None = None, *, missing_package: bool = False) -> None:
        if missing_package:
            detail = (
                "The default deciders live in the optional `notte-llm` package: install it with "
                "`pip install 'notte[llm]'` (or `pip install notte-llm`), or pass `decider=...` explicitly."
            )
        else:
            detail = reason or "No decider is configured."
        message = (
            f"session.act() / choose() / check() need a decider. {detail} "
            "Configure one of: (1) TYPESAFE_API_KEY to use the Jev classification model from TypeSafe "
            "(field values are then written by a small LLM, see NOTTE_ACT_TEXT_MODEL); or "
            "(2) an LLM: OPENROUTER_API_KEY (default model, override with NOTTE_ACT_MODEL), or any "
            "OpenAI-compatible endpoint with NOTTE_LLM_BASE_URL, NOTTE_LLM_API_KEY and NOTTE_ACT_MODEL / NOTTE_LLM_MODEL."
        )
        super().__init__(dev_message=message, user_message=message, agent_message=message)


class InvalidDecisionError(ActError):
    """The decider returned an answer that fails validation. Nothing was executed."""

    def __init__(self, reason: str) -> None:
        message = f"Invalid decider response, no action executed: {reason}"
        super().__init__(dev_message=message, user_message=message, agent_message=message, should_retry_later=True)


class NoActionFoundError(ActError):
    """`act()` found no action to carry out the instruction (decider answered BLOCKED, the confidence was
    below `min_confidence`, or no field value could be written). `result` holds the details."""

    # also `None` on an error rehydrated from its serialized form (`SerializedError.to_exception`)
    result: "ActResult | None" = None

    def __init__(self, instruction: str, reason: str, result: "ActResult | None" = None) -> None:
        message = f"No action found for instruction {instruction!r}: {reason}"
        super().__init__(dev_message=message, user_message=message, agent_message=message)
        self.result = result
