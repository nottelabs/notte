#!/usr/bin/env python3
"""Keep the Quickstart's agent menu, prompt preview, and agent output pointed at the shared setup."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from urllib.parse import quote

SRC_DIR = Path(__file__).resolve().parent.parent
QUICKSTART = SRC_DIR / "quickstart.mdx"
SETUP_PROMPT = "Read https://notte.cc/skill.md and follow its setup instructions."


def render_agent_visibility(prompt: str) -> str:
    return f'<Visibility for="agents">\n\n{prompt.rstrip()}\n\n</Visibility>'


def replace_one(pattern: str, replacement: str, text: str, label: str, flags: int = re.DOTALL) -> str:
    updated, count = re.subn(pattern, lambda _: replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"expected to replace exactly one {label}, replaced {count}")
    return updated


def replace_all(pattern: str, replacement: str, text: str, label: str) -> str:
    updated, count = re.subn(pattern, lambda _: replacement, text)
    if count == 0:
        raise RuntimeError(f"expected to replace at least one {label}, replaced 0")
    return updated


def update_quickstart(text: str, prompt: str) -> str:
    """Point every copy of the prompt on the page at `prompt`.

    The "Connect your agent" menu copies it from each item's data-nv-copy-prompt, the
    Claude Code and Cursor items also pass it URL-encoded in their deep links, the
    prompt box previews it, and agents read the Visibility block.
    """
    encoded = quote(prompt, safe="")
    text = replace_all(
        r'data-nv-copy-prompt="[^"]*"',
        f'data-nv-copy-prompt="{html.escape(prompt, quote=True)}"',
        text,
        "menu copy prompt",
    )
    text = replace_one(
        r'href="claude-cli://open\?q=[^"]*"', f'href="claude-cli://open?q={encoded}"', text, "Claude Code link"
    )
    text = replace_one(
        r'href="https://cursor\.com/link/prompt\?text=[^"]*"',
        f'href="https://cursor.com/link/prompt?text={encoded}"',
        text,
        "Cursor link",
    )
    text = replace_preview(text, prompt)
    text = replace_one(
        r"<Visibility for=\"agents\">\n.*?\n</Visibility>",
        render_agent_visibility(prompt),
        text,
        "agents Visibility block",
    )
    return text.rstrip("\n") + "\n"


def replace_preview(text: str, prompt: str) -> str:
    updated, count = re.subn(
        r'(<div className="nv-qs__prompt">.*?<code>).*?(</code>)',
        lambda m: m.group(1) + html.escape(prompt, quote=False) + m.group(2),
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError(f"expected to replace exactly one prompt preview, replaced {count}")
    return updated


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
