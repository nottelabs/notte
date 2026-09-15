"""`evaluate_js()` returns the evaluated string; the envelope stays on the `False` overload."""

import gc
import weakref

import notte_browser.session as session_module
import pytest
from notte_browser.session import NotteSession
from notte_core.browser.observation import ExecutionResult
from notte_core.common.config import config
from notte_core.errors.actions import ActionExecutionError, EvaluateJsResultLimitError


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


@pytest.mark.asyncio
async def test_large_result_fails_action_and_session_remains_usable(monkeypatch) -> None:
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    code = '() => { let x = {value: "x"}; for(let i=0;i<25;i++) x={left:x,right:x}; return x; }'
    async with NotteSession(headless=True) as session:
        result = await session.aevaluate_js(code, raise_on_failure=False)
        assert result.success is False
        assert isinstance(result.exception, EvaluateJsResultLimitError)
        assert "Return fewer fields" in result.message
        assert result.data is None
        assert await session.aevaluate_js("1 + 1") == "2"
        with pytest.raises(EvaluateJsResultLimitError):
            await session.aevaluate_js(code)


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_on_failure", [False, True])
async def test_saved_limit_errors_do_not_retain_rejected_results(monkeypatch, raise_on_failure) -> None:
    class TrackedList(list):
        pass

    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 1024}))
    references = []
    failures = []
    async with NotteSession(headless=True) as session:
        original_evaluate = session.window.page.evaluate

        async def evaluate(expression, *args, **kwargs):
            if expression == "rejected_result":
                value = TrackedList(["x" * 4096])
                references.append(weakref.ref(value))
                return value
            return await original_evaluate(expression, *args, **kwargs)

        monkeypatch.setattr(session.window.page, "evaluate", evaluate)
        for _ in range(3):
            if raise_on_failure:
                try:
                    await session.aevaluate_js("rejected_result")
                except EvaluateJsResultLimitError as error:
                    failures.append(error)
                else:
                    pytest.fail("expected a result-limit error")
            else:
                failures.append(await session.aevaluate_js("rejected_result", raise_on_failure=False))
        gc.collect()
        assert len(failures) == 3  # Keep errors and the active session trajectory alive.
        assert len(references) == 3
        assert all(reference() is None for reference in references)
