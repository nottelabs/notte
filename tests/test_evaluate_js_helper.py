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


@pytest.mark.asyncio
async def test_getter_values_are_measured_and_read_once(monkeypatch) -> None:
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    async with NotteSession(headless=True) as session:
        transferred: list[int] = []
        original_evaluate = session.window.page.evaluate

        async def evaluate(expression, *args, **kwargs):
            value = await original_evaluate(expression, *args, **kwargs)
            transferred.append(1)
            return value

        monkeypatch.setattr(session.window.page, "evaluate", evaluate)
        big = "({ get data() { return 'x'.repeat(4 * 1024 * 1024); } })"
        result = await session.aevaluate_js(big, raise_on_failure=False)
        assert isinstance(result.exception, EvaluateJsResultLimitError)
        assert transferred == []
        code = "(() => { let reads = 0; return { get a() { reads += 1; return reads; }, get b() { reads += 1; return reads; } }; })()"
        assert await session.aevaluate_js(code) == '{\n  "a": 1,\n  "b": 2\n}'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "new Map([['k', 'é'.repeat(3000)]])",
        "new Set(['é'.repeat(3000)])",
        "new Uint8Array(0)",
        "new Uint8Array([1, 2])",
        "new Float64Array([0.5, -0])",
        "({toJSON() { return {a: 1}; }})",
        "Object.assign(Object.create({toJSON: () => ({a: 1})}), {})",
        "JSON.parse('{\"__proto__\": 1}')",
        "(() => { const a = [1]; return [a, a]; })()",
        "[NaN, Infinity, -0, 10n, undefined, null, true, 'q\"\\\\\\n']",
        "({b: 1, a: 2, 2: 'x', 1: 'y'})",
        "new Date(0)",
        "[new Date(0)]",
        "new Date(NaN)",
        "new Error('boom')",
        "[new Error('boom')]",
        "new URL('https://example.com/a?b=1#c')",
        "/a+b/gi",
        "[/x/, /y/m]",
        "new BigInt64Array([1n, -2n])",
        "new Uint8ClampedArray([300])",
        "document.body",
        "[document, window]",
    ],
)
async def test_guarded_results_match_playwright(monkeypatch, code) -> None:
    # The guard returns a snapshot of the value. Whatever Playwright would
    # have transferred for the original must come out of the snapshot too.
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    async with NotteSession(headless=True) as session:
        native = format_evaluation_result(await session.window.page.evaluate(code), max_bytes=16384)
        assert await session.aevaluate_js(code) == native


@pytest.mark.asyncio
async def test_tiny_budgets_accept_results_that_fit(monkeypatch) -> None:
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 2}))
    async with NotteSession(headless=True) as session:
        assert await session.aevaluate_js("[]") == "[]"
        assert await session.aevaluate_js("new Uint8Array(0)") == "[]"
        assert await session.aevaluate_js("({})") == "{}"


HUGE = "4 * 1024 * 1024"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        f"Object.defineProperty(new Error(''), 'message', {{get: () => 'x'.repeat({HUGE})}})",
        f"Object.assign(new Date(0), {{toJSON: () => 'x'.repeat({HUGE})}})",
        f"Object.assign(new URL('https://example.com'), {{toJSON: () => 'x'.repeat({HUGE})}})",
        f"Object.defineProperty(/a/, 'source', {{get: () => 'x'.repeat({HUGE})}})",
        f"(() => {{ class T extends Uint8Array {{ get length() {{ return 0; }} }} return new T({HUGE}); }})()",
        f"[{{[Symbol.toStringTag]: 'Uint8Array'}}, 'x'.repeat({HUGE})]",
    ],
)
async def test_special_values_cannot_smuggle_data_past_the_guard(monkeypatch, code) -> None:
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    async with NotteSession(headless=True) as session:
        transferred: list[int] = []
        original_evaluate = session.window.page.evaluate

        async def evaluate(expression, *args, **kwargs):
            value = await original_evaluate(expression, *args, **kwargs)
            transferred.append(len(repr(value)))
            return value

        monkeypatch.setattr(session.window.page, "evaluate", evaluate)
        result = await session.aevaluate_js(code, raise_on_failure=False)
        assert result.success is False
        assert isinstance(result.exception, EvaluateJsResultLimitError)
        assert transferred == []


@pytest.mark.asyncio
async def test_error_stack_is_not_transferred(monkeypatch) -> None:
    # Only the message is printed, so a huge stack is neither measured nor sent.
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    async with NotteSession(headless=True) as session:
        transferred: list[int] = []
        original_evaluate = session.window.page.evaluate

        async def evaluate(expression, *args, **kwargs):
            value = await original_evaluate(expression, *args, **kwargs)
            transferred.append(len(repr(value)))
            return value

        monkeypatch.setattr(session.window.page, "evaluate", evaluate)
        code = f"Object.assign(new Error('boom'), {{stack: 'x'.repeat({HUGE})}})"
        assert await session.aevaluate_js(code) == "boom"
        assert transferred and transferred[0] < 100


@pytest.mark.asyncio
async def test_forged_special_types_are_sent_as_plain_objects(monkeypatch) -> None:
    # Only genuine Dates are sent as dates, so a forged tag cannot make
    # Playwright call a page-supplied toJSON after the measurement.
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    async with NotteSession(headless=True) as session:
        transferred: list[int] = []
        original_evaluate = session.window.page.evaluate

        async def evaluate(expression, *args, **kwargs):
            value = await original_evaluate(expression, *args, **kwargs)
            transferred.append(len(repr(value)))
            return value

        monkeypatch.setattr(session.window.page, "evaluate", evaluate)
        code = f"[{{[Symbol.toStringTag]: 'Date', toJSON: () => 'x'.repeat({HUGE})}}]"
        assert await session.aevaluate_js(code) == '[\n  {\n    "toJSON": {}\n  }\n]'
        assert transferred and transferred[0] < 100


@pytest.mark.asyncio
async def test_guard_survives_pages_that_replace_builtins() -> None:
    async with NotteSession(headless=True) as session:
        await session.window.page.evaluate(
            "() => { window.URL = function () {}; window.RegExp = class {}; window.Uint8Array = function () {};"
            " window.Int16Array = Object.defineProperty(function () {}, 'BYTES_PER_ELEMENT', {get() { throw new Error('no'); }}); }",
            isolated_context=False,
        )
        assert await session.aevaluate_js("1 + 1") == "2"
        assert await session.aevaluate_js("({a: [1, 'b']})") == '{\n  "a": [\n    1,\n    "b"\n  ]\n}'


@pytest.mark.asyncio
async def test_getters_named_like_regexp_flags_run_once() -> None:
    async with NotteSession(headless=True) as session:
        code = (
            "(() => { const reads = {}; const o = {};"
            " for (const k of ['global', 'ignoreCase', 'multiline', 'sticky', 'unicode', 'dotAll', 'hasIndices']) {"
            " Object.defineProperty(o, k, {enumerable: true, get() { reads[k] = (reads[k] || 0) + 1; return reads[k]; }}); }"
            " return o; })()"
        )
        result = await session.aevaluate_js(code)
        assert '"global": 1' in result
        assert '"hasIndices": 1' in result
        assert ": 2" not in result


@pytest.mark.asyncio
async def test_unencoded_typed_arrays_and_prototype_pollution(monkeypatch) -> None:
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_bytes": 16384}))
    async with NotteSession(headless=True) as session:
        page = session.window.page
        if await page.evaluate("typeof Float16Array === 'function'"):
            native = format_evaluation_result(await page.evaluate("new Float16Array([1.5, 2])"), max_bytes=16384)
            assert await session.aevaluate_js("new Float16Array([1.5, 2])") == native
        polluted = (
            "(() => { Object.prototype.Uint8Array = {Kind: function () { return new Uint8Array(0); }, width: 1e9};"
            " try { return new Uint8Array(4 * 1024 * 1024); } finally { delete Object.prototype.Uint8Array; } })()"
        )
        result = await session.aevaluate_js(polluted, raise_on_failure=False)
        assert result.success is False
        assert isinstance(result.exception, EvaluateJsResultLimitError)


async def _transfers(session, monkeypatch) -> list[int]:
    transferred: list[int] = []
    original_evaluate = session.window.page.evaluate

    async def evaluate(expression, *args, **kwargs):
        value = await original_evaluate(expression, *args, **kwargs)
        transferred.append(len(repr(value)))
        return value

    monkeypatch.setattr(session.window.page, "evaluate", evaluate)
    return transferred


@pytest.mark.asyncio
async def test_value_cap_counts_every_value(monkeypatch) -> None:
    monkeypatch.setattr(session_module, "config", config.model_copy(update={"evaluate_js_max_result_values": 100}))
    async with NotteSession(headless=True) as session:
        transferred = await _transfers(session, monkeypatch)
        # The array plus 99 numbers is exactly 100 values.
        assert await session.aevaluate_js("Array(99).fill(0)") == format_evaluation_result([0] * 99, max_bytes=16384)
        # Each {a, b} row is 3 values: 33 rows plus the array are 100, 34 rows are 103.
        assert (await session.aevaluate_js("Array.from({length: 33}, () => ({a: 1, b: 'x'}))")).startswith("[")
        transferred.clear()
        # A typed array is one value plus one per element: 99 elements fit, 100 do not.
        assert (await session.aevaluate_js("new Uint8Array(99)")).startswith("[")
        transferred.clear()
        for code in (
            "Array(100).fill(0)",
            "Array.from({length: 34}, () => ({a: 1, b: 'x'}))",
            "new Uint8Array(100)",
            "[new Float64Array(60), new Int8Array(60)]",
        ):
            result = await session.aevaluate_js(code, raise_on_failure=False)
            assert result.success is False
            assert isinstance(result.exception, EvaluateJsResultLimitError)
            assert "more than 100 values" in result.message
        assert transferred == []


@pytest.mark.asyncio
async def test_default_value_cap_rejects_large_row_results_in_the_page(monkeypatch) -> None:
    async with NotteSession(headless=True) as session:
        transferred = await _transfers(session, monkeypatch)
        rows = "Array.from({length: 20000}, (_, i) => ({id: i, name: 'row' + i}))"
        result = await session.aevaluate_js(rows, raise_on_failure=False)
        assert result.success is False
        assert "more than 50000 values" in result.message
        assert transferred == []
        assert (await session.aevaluate_js("Array.from({length: 10000}, (_, i) => ({id: i}))")).startswith("[")
        transferred.clear()
        result = await session.aevaluate_js("new Uint8Array(1000000)", raise_on_failure=False)
        assert "more than 50000 values" in result.message
        assert transferred == []
