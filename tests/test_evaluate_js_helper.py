"""`evaluate_js()` returns the evaluated string; the envelope stays on the `False` overload."""

import gc
import weakref

import notte_browser.session as session_module
import pytest
from notte_browser.evaluation_result import format_evaluation_result
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
            # The user code is the first argument of the page-side guard.
            if args and args[0][0] == "rejected_result":
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


@pytest.mark.asyncio
async def test_expression_forms_keep_their_meaning_behind_the_guard() -> None:
    async with NotteSession(headless=True) as session:
        assert await session.aevaluate_js("const a = 1; a + 1") == "2"
        assert await session.aevaluate_js("() => 3") == "3"
        assert await session.aevaluate_js("function f() { return 4 }") == "4"
        assert await session.aevaluate_js("async () => 5") == "5"
        assert await session.aevaluate_js("Promise.resolve(6)") == "6"
        assert await session.aevaluate_js("return 7") == "7"
        assert await session.aevaluate_js("undefined") == "null"
        assert await session.aevaluate_js("({a: [1, 'b', null]})") == '{\n  "a": [\n    1,\n    "b",\n    null\n  ]\n}'


@pytest.mark.asyncio
async def test_oversized_result_is_rejected_inside_the_page(monkeypatch) -> None:
    # A single large string is cheap for the page to build but, without the
    # guard, every byte would be serialized by the browser, decoded by the
    # driver and copied into Python before the conversion budget ran.
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    async with NotteSession(headless=True) as session:
        transferred: list[int] = []
        original_evaluate = session.window.page.evaluate

        async def evaluate(expression, *args, **kwargs):
            value = await original_evaluate(expression, *args, **kwargs)
            transferred.append(len(str(value)))
            return value

        monkeypatch.setattr(session.window.page, "evaluate", evaluate)
        result = await session.aevaluate_js('"x".repeat(4 * 1024 * 1024)', raise_on_failure=False)
        assert result.success is False
        assert isinstance(result.exception, EvaluateJsResultLimitError)
        assert "serialized result exceeds 16384 bytes" in result.message
        assert transferred == [], "the rejected value must not reach the driver"
        assert await session.aevaluate_js('"y".repeat(100)') == "y" * 100
        assert transferred == [100]


@pytest.mark.asyncio
async def test_guard_works_on_a_page_without_unsafe_eval() -> None:
    # Playwright evaluates expression strings with eval inside the page, and the
    # guard does the same, so a strict script-src policy must not change results.
    async with NotteSession(headless=True) as session:
        await session.window.page.set_content(
            '<html><head><meta http-equiv="Content-Security-Policy" content="script-src \'self\'"></head>'
            "<body><p id='x'>hello</p></body></html>"
        )
        assert await session.aevaluate_js("document.getElementById('x').textContent") == "hello"
        assert await session.aevaluate_js("const n = 2; n * 21") == "42"


@pytest.mark.asyncio
async def test_guard_counts_escaped_width_in_containers_and_utf8_for_text(monkeypatch) -> None:
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    async with NotteSession(headless=True) as session:
        transferred: list[int] = []
        original_evaluate = session.window.page.evaluate

        async def evaluate(expression, *args, **kwargs):
            value = await original_evaluate(expression, *args, **kwargs)
            transferred.append(1)
            return value

        monkeypatch.setattr(session.window.page, "evaluate", evaluate)
        # 3000 characters, but 18002 bytes once escaped as JSON inside a list:
        # a character count would have admitted it.
        result = await session.aevaluate_js('["\u00e9".repeat(3000)]', raise_on_failure=False)
        assert result.success is False
        assert isinstance(result.exception, EvaluateJsResultLimitError)
        assert transferred == []
        # As plain text the same characters are 6000 UTF-8 bytes, within the
        # budget the conversion step applies, so the guard must admit it.
        assert await session.aevaluate_js('"\u00e9".repeat(3000)') == "\u00e9" * 3000
        assert transferred == [1]


@pytest.mark.asyncio
async def test_guard_never_rejects_what_the_formatter_accepts(monkeypatch) -> None:
    # 2500 zeros format to about 12.5 KB of indented JSON, within the budget.
    # A guard charging a fixed size per number would have rejected them.
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    expected = format_evaluation_result([0] * 2500, max_bytes=16384)
    async with NotteSession(headless=True) as session:
        assert await session.aevaluate_js("Array(2500).fill(0)") == expected


@pytest.mark.asyncio
async def test_guard_does_not_call_getters() -> None:
    async with NotteSession(headless=True) as session:
        code = "(() => { let reads = 0; return { get count() { reads += 1; return reads; } }; })()"
        assert await session.aevaluate_js(code) == '{\n  "count": 1\n}'


@pytest.mark.asyncio
async def test_page_errors_that_imitate_the_guard_stay_javascript_failures() -> None:
    async with NotteSession(headless=True) as session:
        result = await session.aevaluate_js(
            "throw new Error('notte_evaluate_js_result_limit:serialized result exceeds 1 bytes')",
            raise_on_failure=False,
        )
        assert result.success is False
        assert not isinstance(result.exception, EvaluateJsResultLimitError)
        assert "JavaScript evaluation failed" in result.message
