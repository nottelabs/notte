"""`evaluate_js()` returns the evaluated string; the envelope stays on the `False` overload."""

import pytest
from notte_browser.session import NotteSession
from notte_core.browser.observation import ExecutionResult
from notte_core.errors.actions import ActionExecutionError


@pytest.mark.asyncio
async def test_aevaluate_js_returns_the_string() -> None:
    async with NotteSession(headless=True) as session:
        assert await session.aevaluate_js("1 + 1") == "2"
        # a JS `null` is a successful evaluation and arrives as the string "null"
        assert await session.aevaluate_js("null") == "null"
        assert await session.aevaluate_js("[1, 2]") == "[\n  1,\n  2\n]"


@pytest.mark.asyncio
async def test_aevaluate_js_failure_raises_the_js_error() -> None:
    async with NotteSession(headless=True) as session:
        with pytest.raises(ActionExecutionError, match="JavaScript evaluation failed"):
            _ = await session.aevaluate_js("notAFunction()")


@pytest.mark.asyncio
async def test_aevaluate_js_returns_the_envelope_when_not_raising() -> None:
    async with NotteSession(headless=True) as session:
        result = await session.aevaluate_js("notAFunction()", raise_on_failure=False)

        assert isinstance(result, ExecutionResult)
        assert result.success is False
        assert result.message.startswith("JavaScript evaluation failed:")


# NOTE: no sync-variant test here on purpose. A sync NotteSession (asyncio.run
# under nest_asyncio) breaks the next async browser launch in the same pytest
# process, so mixing the two in one file flakes under random test ordering.
# The sync wrapper is a one-line delegation to aevaluate_js and its overload
# typing is pinned by typing_cases/evaluate_js_overloads.py.
