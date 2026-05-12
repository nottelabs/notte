#!/usr/bin/env python3
"""Inline the Notte browser skill docs into the Quickstart setup prompt."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent
QUICKSTART = SRC_DIR / "quickstart.mdx"
SKILL_URL = (
    "https://raw.githubusercontent.com/nottelabs/notte-skills/refs/heads/main/"
    "plugins/notte-cli/skills/notte-browser/SKILL.md"
)
SKILL_BLOB_BASE = "https://github.com/nottelabs/notte-skills/blob/main/plugins/notte-cli/skills/notte-browser"


def fetch_skill_docs() -> str:
    request = urllib.request.Request(SKILL_URL, headers={"User-Agent": "notte-docs-inline/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def normalize_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip("\n")


def rewrite_skill_relative_links(text: str) -> str:
    """Make skill-local reference/template links valid from docs pages."""

    def replace_link(match: re.Match[str]) -> str:
        return f"]({SKILL_BLOB_BASE}/{match.group(1)})"

    return re.sub(r"\]\(((?:references|templates)/[^)#\s]+(?:#[^)]+)?)\)", replace_link, text)


def setup_prompt(skill_docs: str) -> str:
    skill_docs = rewrite_skill_relative_links(normalize_markdown(skill_docs))
    sections = [
        "# Setup Notte",
        "",
        "## Goal: Generate a Working SDK Script",
        "",
        "Your end goal is a reliable Python SDK automation script. Generate it with the CLI first, then edit it.",
        "",
        "The Notte CLI is the source of truth for real browser state. Use the Notte skill and CLI to inspect the live site, validate actions/selectors, handle auth/session state, then export workflow code with `notte sessions workflow-code`.",
        "",
        "Use SDK docs only to understand, run, or edit exported workflow code. SDK-first automation is guesswork on real pages with dynamic selectors, auth state, CAPTCHAs, and anti-bot behavior.",
        "",
        "## Agent Rule: Do Not Guess Selectors",
        "",
        "Do not hand-write SDK code with element IDs, selectors, or form fields from memory. Browser targets must come from a live `observe()` call, CLI `notte page observe` output, or generated workflow code. Guessed targets fail on real pages.",
        "",
        "## Agent Rule: Authentication Is Interactive",
        "",
        "Before writing scripts, scaffolding fallback code, or switching approaches, check Notte authentication:",
        "",
        "```bash",
        "notte auth status",
        "```",
        "",
        "If authentication is missing, do not stop, create fallback code, or ask for an API key first. The CLI works in non-interactive terminals; the human may just need to complete browser login. Run:",
        "",
        "```bash",
        "notte auth login",
        "```",
        "",
        'Tell the user: "Please complete the Notte login flow that just opened." Then poll every 5 seconds for up to 5 minutes:',
        "",
        "```bash",
        "notte auth status",
        "```",
        "",
        "Only continue after `notte auth status` succeeds. If login does not complete after 5 minutes, ask whether to retry login or set `NOTTE_API_KEY`.",
        "",
        "Do not generate placeholder automation, SDK scripts, or README-only instructions because Notte is unauthenticated. Authentication is part of the setup workflow.",
        "",
        "## Required CLI-to-SDK Loop",
        "",
        "Complete this loop to generate valid SDK code before using SDK docs or writing SDK code:",
        "",
        "```bash",
        "notte auth status || notte auth login",
        "# If login opens an interactive flow, wait for the user to complete it.",
        "# Then poll `notte auth status` until it succeeds before continuing.",
        "notte auth status",
        "notte sessions start",
        "notte sessions viewer",
        "notte page goto https://target-site.com/",
        "notte page observe",
        "# Use element IDs only after they appear in the observe output. Do not guess IDs.",
        'notte page click "B3"',
        'notte page fill "I1" "example value"',
        'notte page scrape --instructions "Extract the relevant data"',
        "notte sessions workflow-code",
        "```",
        "",
        "## Prerequisites",
        "- Install the Notte skill globally:",
        "",
        "```bash",
        "npx skills add nottelabs/notte-skills -y -g",
        "```",
        "",
        "## Notte Browser Skill Documentation",
        "",
        "Use this inline skill documentation for available commands and capabilities.",
        "",
        skill_docs,
        "",
        "---",
        "",
        "## Installation & Authentication Steps",
        "",
        "### 1. Verify the Notte CLI Installation",
        "",
        "Run:",
        "",
        "```bash",
        "notte -h",
        "```",
        "",
        "If the command is not found, install the CLI with:",
        "",
        "```bash",
        "brew tap nottelabs/notte-cli https://github.com/nottelabs/notte-cli.git",
        "brew install notte",
        "```",
        "",
        "---",
        "",
        "### 2. Check Authentication Status",
        "",
        "Run:",
        "",
        "```bash",
        "notte auth status",
        "```",
        "",
        "- If you are already authenticated, continue to the next step.",
        "- If authentication is required, run:",
        "",
        "```bash",
        "notte auth login",
        "```",
        "",
        "Complete the login flow in your browser.",
        "",
        "Then poll the authentication status every 5 seconds for up to 5 minutes:",
        "",
        "```bash",
        "notte auth status",
        "```",
        "",
        "If authentication does not complete after 5 minutes, stop and ask the user for assistance.",
        "",
        "---",
        "",
        "### 3. Start a Browser Session",
        "",
        "Launch a browser session, open the viewer, and navigate to the documentation site:",
        "",
        "```bash",
        "notte sessions start && notte sessions viewer && notte page goto https://docs.notte.cc/",
        "```",
        "",
        "Echo the session viewer url to the user in case the page doesn't automatically open on their desktop.",
    ]
    return "\n".join(sections).rstrip() + "\n"


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
        skill_docs = fetch_skill_docs()
    except Exception as error:
        if args.check:
            print(
                f"warning: could not fetch Notte browser skill docs; skipping quickstart setup prompt check ({error})",
                file=sys.stderr,
            )
            return 0
        print(f"failed to fetch Notte browser skill docs: {error}", file=sys.stderr)
        return 1

    try:
        prompt = setup_prompt(skill_docs)
        original = QUICKSTART.read_text(encoding="utf-8")
        updated = update_quickstart(original, prompt)
    except Exception as error:
        print(f"failed to inline quickstart setup prompt: {error}", file=sys.stderr)
        return 1

    if updated == original:
        print("quickstart setup prompt is up to date")
        return 0

    if args.check:
        print("quickstart setup prompt is out of date")
        print(f"run: cd {SRC_DIR} && uv run python scripts/inline_quickstart_setup_prompt.py")
        return 1

    QUICKSTART.write_text(updated, encoding="utf-8")
    print(f"updated {QUICKSTART.relative_to(SRC_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
