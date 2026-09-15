import datetime as dt
import json
import tracemalloc

import pytest
from notte_browser.evaluation_result import format_evaluation_result
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
