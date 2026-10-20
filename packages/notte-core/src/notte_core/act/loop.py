"""A minimal loop over `session.act()`: repeat one instruction until it is done, with two guards.

Not an agent: one instruction, no planning. It stops when the decider answers DONE or BLOCKED, after
`max_steps` actions, or when three actions in a row (other than WAIT) left the page unchanged.
"""

from typing import Any, Protocol

from notte_core.act.types import ActResult

UNCHANGED_LIMIT = 3


class SupportsAct(Protocol):
    def act(self, instruction: str, /, **kwargs: Any) -> ActResult: ...


class SupportsAact(Protocol):
    async def aact(self, instruction: str, /, **kwargs: Any) -> ActResult: ...


def _stop(results: list[ActResult]) -> bool:
    last = results[-1]
    if last.status != "executed":
        return True
    # the page each decision was taken on: identical fingerprints mean the actions in between changed nothing
    recent = results[-(UNCHANGED_LIMIT + 1) :]
    return (
        len(recent) == UNCHANGED_LIMIT + 1
        and all(r.fingerprint is not None for r in recent)
        and len({r.fingerprint for r in recent}) == 1
        and all(r.operation != "WAIT" for r in recent[:-1])
    )


def act_until_done(session: SupportsAct, instruction: str, *, max_steps: int = 20, **kwargs: Any) -> list[ActResult]:
    """Call `session.act(instruction)` until DONE / BLOCKED / stale, `max_steps`, or 3 unchanged actions."""
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
