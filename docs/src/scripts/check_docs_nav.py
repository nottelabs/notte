#!/usr/bin/env python3
"""Check `docs.json` navigation entries for conflicting link and child fields.

A navigation entry is either a link (`href`) or a container of nested pages
(`groups`, `pages`, `menu`, `anchors`, `tabs`, `dropdowns`, `versions`,
`languages`). Mintlify treats those as mutually exclusive: when an entry
declares both, the build keeps the link and silently drops every nested page,
so the entry becomes a dead link and its pages lose their sidebar.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parent.parent
DOCS_JSON = SRC_DIR / "docs.json"
CHILD_FIELDS = (
    "anchors",
    "dropdowns",
    "groups",
    "languages",
    "menu",
    "pages",
    "tabs",
    "versions",
)
LABEL_FIELDS = ("tab", "group", "anchor", "dropdown", "language", "version")


def label(entry: dict[str, Any]) -> str:
    for field in LABEL_FIELDS:
        value = entry.get(field)
        if isinstance(value, str):
            return f"{field} '{value}'"
    return "navigation entry"


def check(node: Any, path: str, errors: list[str]) -> None:
    if isinstance(node, list):
        for index, item in enumerate(node):
            check(item, f"{path}[{index}]", errors)
        return
    if not isinstance(node, dict):
        return

    children = [field for field in CHILD_FIELDS if field in node]
    if "href" in node and children:
        errors.append(
            f"{path}: {label(node)} declares both 'href' and {', '.join(repr(c) for c in children)}. "
            "Drop 'href' so the nested pages survive the build."
        )

    for key, value in node.items():
        check(value, f"{path}.{key}", errors)


def main() -> int:
    navigation = json.loads(DOCS_JSON.read_text())["navigation"]
    errors: list[str] = []
    check(navigation, "navigation", errors)
    for error in errors:
        print(f"docs.json: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
