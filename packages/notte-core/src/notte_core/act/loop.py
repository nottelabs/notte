"""A minimal loop over `session.act()`: repeat one instruction until it is done, with two guards.

Not an agent: one instruction, no planning. It stops when the decider answers DONE or BLOCKED, after
`max_steps` actions, when three actions in a row (other than WAIT and scrolls) left the page unchanged, or when the
last four actions alternate between two on the same element (A, B, A, B: a select set to 1900, 1901, 1900, 1901),
which change the page each time without getting anywhere.
"""

from typing import Any, Protocol

from notte_core.act.types import ActResult

UNCHANGED_LIMIT = 3
# A, B, A, B
ALTERNATION_LENGTH = 4
# the fingerprint leaves out the scroll position, and WAIT is expected to change nothing at first
_UNTRACKED_OPERATIONS = ("WAIT", "SCROLL_DOWN", "SCROLL_UP")


class SupportsAct(Protocol):
    def act(self, instruction: str, /, **kwargs: Any) -> ActResult: ...


class SupportsAact(Protocol):
    async def aact(self, instruction: str, /, **kwargs: Any) -> ActResult: ...


def _alternating(results: list[ActResult]) -> bool:
    """The last `ALTERNATION_LENGTH` actions alternate between two different actions on the same element."""
    recent = results[-ALTERNATION_LENGTH:]
    if len(recent) < ALTERNATION_LENGTH or any(r.status != "executed" or r.action is None for r in recent):
        return False
    a, b = recent[-2].action, recent[-1].action
    elements = {getattr(r.action, "id", None) for r in recent}
    return (
        a != b
        and len(elements) == 1
        and None not in elements
        and all(r.action == (a if i % 2 == 0 else b) for i, r in enumerate(recent))
    )


def _stop(results: list[ActResult]) -> bool:
    last = results[-1]
    if last.status != "executed" or _alternating(results):
        return True
    # the page each decision was taken on: identical fingerprints mean the actions in between changed nothing
    recent = results[-(UNCHANGED_LIMIT + 1) :]
    return (
        len(recent) == UNCHANGED_LIMIT + 1
        and all(r.fingerprint is not None for r in recent)
        and len({r.fingerprint for r in recent}) == 1
        and all(r.operation not in _UNTRACKED_OPERATIONS for r in recent[:-1])
    )


def act_until_done(session: SupportsAct, instruction: str, *, max_steps: int = 20, **kwargs: Any) -> list[ActResult]:
    """Call `session.act(instruction)` until DONE / BLOCKED / stale, `max_steps`, 3 unchanged actions
    (WAIT and scrolls aside), or 4 actions alternating on one element."""
    results: list[ActResult] = []
    for _ in range(max_steps):
        results.append(session.act(instruction, raise_on_failure=False, **kwargs))
        if _stop(results):
            break
    return results


async def aact_until_done(
    session: SupportsAact, instruction: str, *, max_steps: int = 20, **kwargs: Any
) -> list[ActResult]:
    """Async version of `act_until_done`."""
    results: list[ActResult] = []
    for _ in range(max_steps):
        results.append(await session.aact(instruction, raise_on_failure=False, **kwargs))
        if _stop(results):
            break
    return results
