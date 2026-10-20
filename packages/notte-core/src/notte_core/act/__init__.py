"""`session.act()`, `choose()` and `check()`: one action from a natural-language instruction.

The model-agnostic part lives here: the questions asked about an observed page, the strict
validation of the answers, the mapping back to notte actions and the guards. Deciders (Jev, LLM)
live in `notte-llm`; sessions plug in through `ActDriver`.
"""

from notte_core.act.errors import DeciderNotAvailableError, InvalidDecisionError, NoActionFoundError
from notte_core.act.loop import aact_until_done, act_until_done
from notte_core.act.resolve import default_decider
from notte_core.act.runner import ActDriver, ActHistory, run_act, run_check, run_choose, same_target
from notte_core.act.space import ObservedPage
from notte_core.act.types import (
    ActResult,
    ActStatus,
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

__all__ = [
    "ActDriver",
    "ActHistory",
    "ActResult",
    "ActStatus",
    "ActTimings",
    "Answer",
    "Answers",
    "Choice",
    "Decider",
    "DeciderNotAvailableError",
    "DecisionState",
    "InvalidDecisionError",
    "NoActionFoundError",
    "ObservedPage",
    "PageState",
    "Question",
    "WriteContext",
    "aact_until_done",
    "act_until_done",
    "default_decider",
    "run_act",
    "run_check",
    "run_choose",
    "same_target",
]
