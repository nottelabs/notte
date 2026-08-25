#!/usr/bin/env python3
"""Check documented session-config defaults against the SDK's actual values.

`docs/src/features/sessions/configuration.mdx` is hand-written, so its
`<ParamField default={...}>` values can silently drift from the code (the page
said `raise_on_failure` defaults to false for seven months while the config
said true). This check compares every documented default against the source of
truth: `SessionStartRequest` field defaults and `notte_core` config values.

Doc param names do not always match field names one-to-one, so the mapping in
`code_defaults()` is explicit; a documented default with no mapping entry is an
error, which forces the mapping to grow with the page.

Run from the repo root (the script needs the workspace venv for notte imports):
    uv run python docs/src/scripts/check_config_docs_defaults.py
"""

from __future__ import annotations

import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIGURATION_MDX = REPO_ROOT / "docs" / "src" / "features" / "sessions" / "configuration.mdx"

PARAM_FIELD_RE = re.compile(r'<ParamField\s+path="([^"]+)"[^>]*?\sdefault=(\{[^}]*\}|"[^"]*")')


def code_defaults() -> dict[str, Any]:
    from notte_core.common.config import config
    from notte_sdk.types import (
        DEFAULT_HEADLESS_VIEWPORT_HEIGHT,
        DEFAULT_HEADLESS_VIEWPORT_WIDTH,
        SessionStartRequest,
    )

    fields = SessionStartRequest.model_fields

    def field_default(name: str) -> Any:
        return fields[name].default

    return {
        "headless": field_default("headless"),
        "solve_captchas": field_default("solve_captchas"),
        "proxies": field_default("proxies"),
        # the docs param is the SDK's idle timeout
        "timeout_minutes": field_default("idle_timeout_minutes"),
        # the request fields default to None ("server decides"); the effective
        # server defaults are these shared constants
        "viewport_width": DEFAULT_HEADLESS_VIEWPORT_WIDTH,
        "viewport_height": DEFAULT_HEADLESS_VIEWPORT_HEIGHT,
        "browser_type": field_default("browser_type"),
        "use_file_storage": field_default("use_file_storage"),
        "perception_type": config.perception_type,
        "raise_on_failure": config.raise_on_session_execution_failure,
    }


def parse_doc_default(token: str) -> Any:
    """Turn a ParamField default token (`{true}`, `{3}`, `{"chrome"}`, `"fast"`) into a value."""
    if token.startswith('"'):
        return token[1:-1]
    inner = token[1:-1].strip()
    if inner == "true":
        return True
    if inner == "false":
        return False
    if inner.startswith('"') and inner.endswith('"'):
        return inner[1:-1]
    try:
        return int(inner)
    except ValueError:
        return inner


def normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def main() -> int:
    text = CONFIGURATION_MDX.read_text()
    expected = code_defaults()
    errors: list[str] = []
    checked = 0

    for match in PARAM_FIELD_RE.finditer(text):
        name, token = match.group(1), match.group(2)
        doc_value = parse_doc_default(token)
        if name not in expected:
            errors.append(
                f"{name}: documented default {doc_value!r} has no entry in code_defaults(); "
                "add a mapping to the code's source of truth"
            )
            continue
        checked += 1
        code_value = normalize(expected[name])
        if doc_value != code_value or isinstance(doc_value, bool) is not isinstance(code_value, bool):
            errors.append(f"{name}: docs say {doc_value!r}, code default is {code_value!r}")

    if checked == 0:
        errors.append(f"no ParamField defaults found in {CONFIGURATION_MDX}; the regex or the page drifted")

    if errors:
        print(f"{CONFIGURATION_MDX.relative_to(REPO_ROOT)} disagrees with the SDK defaults:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"checked {checked} documented defaults against the SDK: all match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
