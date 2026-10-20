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
            "Configure one of: (1) OPENROUTER_API_KEY to use TypeSafe's Jev classification model through "
            "OpenRouter, with field values written by a small LLM on OpenRouter (see NOTTE_ACT_TEXT_MODEL); "
            "(2) TYPESAFE_API_KEY to call Jev on TypeSafe directly (an OpenRouter key is still needed to type "
            "text); or (3) an LLM decider on any OpenAI-compatible endpoint: NOTTE_LLM_BASE_URL, NOTTE_LLM_API_KEY "
            "and NOTTE_ACT_MODEL / NOTTE_LLM_MODEL (NOTTE_ACT_DECIDER=llm selects it on OpenRouter)."
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
