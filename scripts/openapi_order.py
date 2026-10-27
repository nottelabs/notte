"""Order-insensitive copies for schema comparison, never for generated output.

Match ECMAScript's JSON key order: array indices numerically, then other keys
lexically by UTF-16 code units. Array elements are never reordered.
"""

from __future__ import annotations

import json
from typing import TypeAlias

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def _key_order(key: str) -> tuple[int, int, bytes]:
    # ECMAScript array indices are canonical decimal strings below 2**32 - 1.
    if key.isascii() and key.isdecimal() and len(key) <= 10:
        index = int(key)
        if index < 2**32 - 1 and str(index) == key:
            return (0, index, b"")
    return (1, 0, key.encode("utf-16-be", errors="surrogatepass"))


def _comparison_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {key: _comparison_value(value[key]) for key in sorted(value, key=_key_order)}
    if isinstance(value, list):
        return [_comparison_value(item) for item in value]
    return value


def comparison_json(value: JsonValue) -> str:
    return json.dumps(_comparison_value(value), indent=2, ensure_ascii=False) + "\n"
