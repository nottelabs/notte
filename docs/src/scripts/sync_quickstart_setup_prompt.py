#!/usr/bin/env python3
"""Keep Quickstart copy, preview, and agent output pointed at the shared setup."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent
QUICKSTART = SRC_DIR / "quickstart.mdx"
SETUP_PROMPT = "Read https://notte.cc/skill.md and follow its setup instructions."


def render_clipboard_prompt(prompt: str) -> str:
    lines = prompt.rstrip("\n").split("\n")
    rendered_lines = ",\n".join(f"          {json.dumps(line)}" for line in lines)
    return (
        f'        const notteSetupPrompt = [\n{rendered_lines}\n        ].join("\\n");\n\n'
        "        navigator.clipboard.writeText(notteSetupPrompt);"
    )


def render_accordion(prompt: str) -> str:
    indented = "\n".join(f"    {line}" if line else "" for line in prompt.rstrip("\n").split("\n"))
    return f"""<Accordion title="View setup prompt">
    ````markdown
{indented}
    ````
  </Accordion>"""


def render_agent_visibility(prompt: str) -> str:
    return f'<Visibility for="agents">\n\n{prompt.rstrip()}\n\n</Visibility>'


def replace_one(pattern: str, replacement: str, text: str, label: str, flags: int = re.DOTALL) -> str:
    updated, count = re.subn(pattern, lambda _: replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"expected to replace exactly one {label}, replaced {count}")
    return updated


def remove_top_level_js_prompt(text: str) -> str:
    return re.sub(
        r"\n*export const notteSetupPrompt = \[\n.*?\n\]\.join\(\"\\n\"\);\n*",
        "\n\n",
        text,
        count=1,
        flags=re.DOTALL,
    )


def update_quickstart(text: str, prompt: str) -> str:
    text = remove_top_level_js_prompt(text)
    text = replace_one(
        r"(?:        const notteSetupPrompt = \[\n.*?\n        \]\.join\(\"\\n\"\);\n\n)?        navigator\.clipboard\.writeText\(notteSetupPrompt\);",
        render_clipboard_prompt(prompt),
        text,
        "clipboard setup prompt",
    )
    text = replace_one(
        r"<Accordion title=\"View setup prompt\">\n.*?\n  </Accordion>",
        render_accordion(prompt),
        text,
        "setup prompt accordion",
    )
    text = replace_one(
        r"<Visibility for=\"agents\">\n.*?\n</Visibility>",
        render_agent_visibility(prompt),
        text,
        "agents Visibility block",
    )
    return text.rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if quickstart.mdx needs updates")
    args = parser.parse_args()

    try:
        original = QUICKSTART.read_text(encoding="utf-8")
        updated = update_quickstart(original, SETUP_PROMPT)
    except (OSError, RuntimeError) as error:
        print(f"failed to update quickstart setup prompt: {error}", file=sys.stderr)
        return 1

    if updated == original:
        print("quickstart setup prompt is up to date")
        return 0
    if args.check:
        print("quickstart setup prompt is out of date")
        print(f"run: cd {SRC_DIR} && python scripts/sync_quickstart_setup_prompt.py")
        return 1

    QUICKSTART.write_text(updated, encoding="utf-8")
    print("updated quickstart.mdx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
