import datetime as dt
import json
import math
import tracemalloc
from urllib.parse import urlparse

import pytest
from notte_browser.evaluation_result import (
    PAGE_RESULT_GUARD,
    RESULT_LIMIT_MARKER,
    decode_page_result,
    format_evaluation_result,
    new_guard_token,
    page_expression,
    page_limit_reason,
)
from notte_core.errors.actions import EvaluateJsResultLimitError


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        [1, True, None, -0.0, float("inf"), float("nan")],
        {"nested": [[], {}, {'quote"': "\n\\\t😀é\ud800"}]},
        {None: 1, False: 2, 3: 4, 2.5: 6},
        [dt.datetime(2026, 9, 15), (1, "two"), b"\x00\xff"],
        ["a" * 8191 + "😀" + "é" * 8193],
    ],
)
def test_matches_existing_json(value):
    expected = json.dumps(value, indent=2, default=str)
    assert format_evaluation_result(value, max_bytes=len(expected)) == expected
    with pytest.raises(EvaluateJsResultLimitError):
        format_evaluation_result(value, max_bytes=len(expected) - 1)


@pytest.mark.parametrize("value", [None, True, 42, "", "hello", "é😀", (1, 2)])
def test_preserves_scalar_text(value):
    expected = "null" if value is None else str(value)
    assert format_evaluation_result(value, max_bytes=max(1, len(expected.encode()))) == expected


def test_scalar_budget_counts_utf8_bytes():
    with pytest.raises(EvaluateJsResultLimitError):
        format_evaluation_result("😀", max_bytes=3)


def test_shared_references_are_repeated_within_budget():
    child = {"value": [1, 2]}
    graph = {"left": child, "right": child}
    assert format_evaluation_result(graph, max_bytes=1024) == json.dumps(graph, indent=2)


def test_exponential_graph_stops_at_budget():
    graph = {"value": "x"}
    for _ in range(30):
        graph = {"left": graph, "right": graph}
    with pytest.raises(EvaluateJsResultLimitError, match="Return fewer fields"):
        format_evaluation_result(graph, max_bytes=64 * 1024)


def test_large_escaped_string_does_not_allocate_entire_encoded_chunk():
    value = ["\x00" * (16 * 1024 * 1024)]
    tracemalloc.start()
    try:
        with pytest.raises(EvaluateJsResultLimitError):
            format_evaluation_result(value, max_bytes=1024 * 1024)
        _, peak = tracemalloc.get_traced_memory()
        # An ordinary encoder first allocates the complete ~96 MiB escaped string.
        assert peak < 8 * 1024 * 1024
    finally:
        tracemalloc.stop()


def test_cycles_keep_existing_error():
    value = []
    value.append(value)
    with pytest.raises(ValueError, match="Circular reference detected"):
        format_evaluation_result(value, max_bytes=1024)


def test_oversized_binary_value_is_rejected_before_string_conversion():
    class Binary(bytes):
        def __str__(self):
            raise AssertionError("must reject before allocating repr")

    with pytest.raises(EvaluateJsResultLimitError):
        format_evaluation_result([Binary(b"a" * 1025)], max_bytes=1024)


def test_excessive_depth_returns_action_error():
    value = []
    for _ in range(130):
        value = [value]
    with pytest.raises(EvaluateJsResultLimitError, match="nesting depth"):
        format_evaluation_result(value, max_bytes=1024 * 1024)


def test_invalid_dict_key_keeps_existing_error():
    with pytest.raises(TypeError, match="keys must be"):
        format_evaluation_result({(1, 2): "value"}, max_bytes=1024)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("1 + 1", "1 + 1"),
        ("  1 + 1\n", "1 + 1"),
        ("() => 1", "() => 1"),
        ("(function () { return 1 })()", "(function () { return 1 })()"),
        ("function f() { return 1 }", "(function f() { return 1 })"),
        ("async function f() { return 1 }", "(async function f() { return 1 })"),
        ("function(){ return 1 }", "(function(){ return 1 })"),
        ("functionName()", "functionName()"),
    ],
)
def test_page_expression_matches_playwright_normalization(code, expected):
    assert page_expression(code) == expected


def test_page_limit_reason_requires_this_evaluations_token():
    token = new_guard_token()
    message = f"Page.evaluate: Error: {RESULT_LIMIT_MARKER}{token}:serialized result exceeds 16 bytes\n    at eval"
    assert page_limit_reason(message, token) == "serialized result exceeds 16 bytes"
    assert page_limit_reason(message, new_guard_token()) is None
    assert page_limit_reason(f"Page.evaluate: Error: {RESULT_LIMIT_MARKER}x", token) is None
    assert page_limit_reason("Page.evaluate: TypeError: boom", token) is None


def test_guard_tokens_are_unique():
    assert len({new_guard_token() for _ in range(100)}) == 100


def test_page_guard_is_a_function_taking_code_budgets_and_token():
    assert PAGE_RESULT_GUARD.startswith("async ([code, maxBytes, maxValues, token]) =>")
    assert RESULT_LIMIT_MARKER in PAGE_RESULT_GUARD


def test_decode_page_result_restores_playwright_values():
    token = new_guard_token()
    text = json.dumps(
        {
            "nan": {token: "n", "v": "NaN"},
            "neg0": {token: "n", "v": "-0"},
            "inf": [{token: "n", "v": "Infinity"}, {token: "n", "v": "-Infinity"}],
            "big": {token: "bi", "v": "18446744073709551615"},
            "date": {token: "d", "v": "2026-10-01T12:00:00.123Z"},
            "invalid_date": {token: "d", "v": None},
            "url": {token: "u", "v": "https://example.com/a?b=1#c"},
            "lookalike": {"other-token": "n", "v": "NaN"},
            "plain": {"v": 1},
        }
    )
    value = decode_page_result("j" + text, token, max_bytes=1 << 20, max_values=1000)
    assert math.isnan(value["nan"])
    assert str(value["neg0"]) == "-0.0"
    assert value["inf"] == [math.inf, -math.inf]
    assert value["big"] == 18446744073709551615
    assert value["date"] == dt.datetime(2026, 10, 1, 12, 0, 0, 123000, tzinfo=dt.timezone.utc)
    assert value["invalid_date"] == dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    assert value["url"] == urlparse("https://example.com/a?b=1#c")
    assert value["lookalike"] == {"other-token": "n", "v": "NaN"}
    assert value["plain"] == {"v": 1}


def test_decode_page_result_checks_the_payload_before_parsing():
    token = new_guard_token()
    assert decode_page_result("s" + "é" * 10, token, max_bytes=100, max_values=10) == "é" * 10
    with pytest.raises(EvaluateJsResultLimitError):
        decode_page_result("s" + "x" * 101, token, max_bytes=100, max_values=10)
    with pytest.raises(EvaluateJsResultLimitError):
        decode_page_result("j" + json.dumps(["x" * 2000]), token, max_bytes=100, max_values=10)
    with pytest.raises(ValueError):
        decode_page_result({"not": "a string"}, token, max_bytes=100, max_values=10)
