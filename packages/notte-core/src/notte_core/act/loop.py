"""A minimal loop over `session.act()`: repeat one instruction until it is done, with three guards.

Not an agent: one instruction, no planning. It stops when the decider answers DONE or BLOCKED, after
`max_steps` actions, when three actions in a row (other than WAIT and scrolls) left the page unchanged, or when the
last four actions alternate between two on the same element (A, B, A, B: a select set to 1900, 1901, 1900, 1901),
which change the page each time without getting anywhere, or when the same action ran on the same page three times
within the last twelve: a cycle through several pages or elements (Checkout, then back from the sign-in page it
opens; Continue, then a scroll, on a form that does not submit; scrolling down and up again). It also stops after five
WAITs in a row through which the page changed nothing, its text included: a page that never renders does not start
rendering by waiting longer.
"""

from collections.abc import Sequence
from typing import Any, Protocol

from notte_core.act.types import ActResult
from notte_core.act.wait import waited_for_nothing

UNCHANGED_LIMIT = 3
# A, B, A, B
ALTERNATION_LENGTH = 4
# the fingerprint leaves out the scroll position, and WAIT is expected to change nothing at first
_UNTRACKED_OPERATIONS = ("WAIT", "SCROLL_DOWN", "SCROLL_UP")
# the same action on the same page (same fingerprint) this many times: twice can be a retry, three times is a cycle
REPEAT_LIMIT = 3
# long enough to hold three turns of a four-step cycle, short enough that a form revisited later is not counted
REPEAT_WINDOW = 12
_SCROLLS = ("SCROLL_DOWN", "SCROLL_UP")
# scrolls both ways this many times each within `REPEAT_WINDOW` actions, whatever the page: lazy content and sticky
# banners change the fingerprint as the page scrolls, so a back-and-forth does not always land on the same page
SCROLL_BACK_AND_FORTH = 4
# direction changes a run of scrolls needs to be a back-and-forth: down, up, then down again. Totals alone are not:
# three down then two up to reach a button above a field reverses once
SCROLL_REVERSALS = 2
# WAITs in a row through which the page did not change: a page still loading changes within a few (each waits up to a
# few seconds for a change); on a guest-checkout benchmark no run that went on to finish waited more than twice in a row
WAIT_LIMIT = 5


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


def _repeat_key(result: ActResult) -> tuple[str | None, ...] | None:
    """What makes two actions the same: the page they were decided on, the operation, its target and text. None for
    an action that is expected to repeat (WAIT) or whose page is not known."""
    if result.status != "executed" or result.fingerprint is None or result.operation in (None, "WAIT"):
        return None
    # scrolling down and up on one page is one back-and-forth; scrolling down alone reads a long page (below)
    operation = "SCROLL" if result.operation in _SCROLLS else result.operation
    return (result.fingerprint, operation, result.target, result.value)


def _reversals(operations: Sequence[str | None]) -> int:
    return sum(1 for a, b in zip(operations, operations[1:]) if a != b)


def _repeating(results: list[ActResult]) -> bool:
    """The last action ran on the same page `REPEAT_LIMIT` times within the last `REPEAT_WINDOW` actions: the run
    goes round a cycle (A, B, A, B, A or A, B, C, A, B, C, A), whatever its length. Scrolls count once they go both
    ways on that page: down `REPEAT_LIMIT` times and up `REPEAT_LIMIT - 1` times, or the reverse; or both ways
    `SCROLL_BACK_AND_FORTH` times each on any page; either way changing direction `SCROLL_REVERSALS` times."""
    key = _repeat_key(results[-1])
    if key is None:
        return False
    recent = results[-REPEAT_WINDOW:]
    if key[1] == "SCROLL":
        scrolls = [r.operation for r in recent if r.status == "executed" and r.operation in _SCROLLS]
        if (
            min(scrolls.count("SCROLL_DOWN"), scrolls.count("SCROLL_UP")) >= SCROLL_BACK_AND_FORTH
            and _reversals(scrolls) >= SCROLL_REVERSALS
        ):
            return True
    same = [r.operation for r in recent if _repeat_key(r) == key]
    if key[1] != "SCROLL":
        first = next(i for i, r in enumerate(recent) if _repeat_key(r) == key)
        # an action repeated on a page that never changed is the unchanged-page guard's (`_stop`), unless scrolls or
        # WAITs came in between, which that guard skips
        return len(same) >= REPEAT_LIMIT and any(
            r.fingerprint != key[0] or r.operation in _UNTRACKED_OPERATIONS for r in recent[first:]
        )
    down, up = same.count("SCROLL_DOWN"), same.count("SCROLL_UP")
    return max(down, up) >= REPEAT_LIMIT and min(down, up) >= REPEAT_LIMIT - 1 and _reversals(same) >= SCROLL_REVERSALS


def _waiting(results: list[ActResult]) -> bool:
    """`WAIT_LIMIT` WAITs in a row through which the page changed nothing, both while each WAIT watched it (its DOM,
    text included, and its URL) and between them, while act observed and decided: the decision after the last of
    them, a WAIT again, was taken on the page the first was (same fingerprint). Any other action, a WAIT that saw a
    change ("Preparing report: 40%"), or a page that changed between two WAITs starts the count again."""
    recent = results[-(WAIT_LIMIT + 1) :]
    return (
        len(recent) == WAIT_LIMIT + 1
        and all(r.status == "executed" and r.operation == "WAIT" for r in recent)
        and all(waited_for_nothing(r.execution) for r in recent[:-1])
        and all(r.fingerprint is not None for r in recent)
        and len({r.fingerprint for r in recent}) == 1
    )


def _stop(results: list[ActResult]) -> bool:
    last = results[-1]
    if last.status != "executed" or _alternating(results) or _repeating(results) or _waiting(results):
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
    (WAIT and scrolls aside), 4 actions alternating on one element, the same action on the same page 3 times
    within 12 actions, or 5 WAITs in a row through which the page changed nothing."""
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
