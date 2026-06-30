#!/usr/bin/env python3
"""Generate src/llms.txt from docs.json navigation structure.

Tabs become H1, top-level groups become H2, nested groups become H3.
Each page is emitted as a bullet with title + description pulled from
the page's YAML frontmatter.

Run from anywhere:
    python3 src/scripts/generate_llms.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

SITE_URL = "https://docs.notte.cc"
SRC_DIR = Path(__file__).resolve().parent.parent
DOCS_JSON = SRC_DIR / "docs.json"
OUTPUT = SRC_DIR / "llms.txt"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}

AGENT_READING_GUIDANCE = [
    "## Critical Instructions For AI Agents",
    "",
    "STOP. Read and follow https://docs.notte.cc/quickstart.md before using SDK docs or writing SDK code.",
    "",
    "Goal: generate a reliable SDK automation script, then edit it. Do not hand-author the first pass from SDK "
    "reference pages.",
    "",
    "The Notte CLI is the source of truth for real browser state. You MUST use the Notte skill and CLI to inspect "
    "the live site, validate actions/selectors, handle auth/session state, and export workflow code with "
    "`notte sessions workflow-code`.",
    "",
    "Use SDK docs only to understand, run, or edit exported workflow code. SDK-first automation is guesswork on "
    "real pages with dynamic selectors, auth state, CAPTCHAs, and anti-bot behavior.",
    "",
    "## Agent Rule: Do Not Guess Selectors",
    "",
    "Do not hand-write SDK code with element IDs, selectors, or form fields from memory. Browser targets must come "
    "from a live `observe()` call, CLI `notte page observe` output, or generated workflow code. Guessed targets "
    "fail on real pages.",
    "",
    "## Agent Rule: Authentication Is Interactive",
    "",
    "Before writing scripts, scaffolding fallback code, or switching approaches, check Notte authentication:",
    "",
    "```bash",
    "notte auth status",
    "```",
    "",
    "If authentication is missing, do not stop, create fallback code, or ask for an API key first. The CLI works in "
    "non-interactive terminals; the human may just need to complete browser login. Run:",
    "",
    "```bash",
    "notte auth login",
    "```",
    "",
    'Tell the user: "Please complete the Notte login flow that just opened." Then poll every 5 seconds for up to 5 '
    "minutes:",
    "",
    "```bash",
    "notte auth status",
    "```",
    "",
    "Only continue after `notte auth status` succeeds. If login does not complete after 5 minutes, ask whether to "
    "retry login or set `NOTTE_API_KEY`.",
    "",
    "Do not generate placeholder automation, SDK scripts, or README-only instructions because Notte is "
    "unauthenticated. Authentication is part of the setup workflow.",
    "",
    "## CLI-First Workflow",
    "",
    "Complete this loop to generate valid SDK code before using SDK documentation or writing SDK code:",
    "",
    "```bash",
    "# 1. Install the CLI if needed",
    "brew tap nottelabs/notte-cli https://github.com/nottelabs/notte-cli.git",
    "brew install notte",
    "# or: go install github.com/nottelabs/notte-cli/cmd/notte@latest",
    "",
    "# 2. Authenticate. If this opens a browser login, wait for the user to finish.",
    "notte auth status || notte auth login",
    "# If login opens an interactive flow, wait for the user to complete it.",
    "# Then poll `notte auth status` until it succeeds before continuing.",
    "notte auth status",
    "",
    "# 3. Start a session, open the viewer, and navigate to the target page",
    "notte sessions start",
    "notte sessions viewer",
    "notte page goto https://target-site.com/",
    "",
    "# 4. Observe the live page and execute actions from real browser state",
    "notte page observe",
    "# Use element IDs only after they appear in the observe output. Do not guess IDs.",
    'notte page click "B3"',
    'notte page fill "I1" "example value"',
    'notte page scrape --instructions "Extract the relevant data"',
    "",
    "# 5. Export workflow code only after CLI exploration",
    "notte sessions workflow-code",
    "```",
    "",
    "Full Quickstart: https://docs.notte.cc/quickstart.md",
    "",
]

SDK_READING_GATE = [
    "## SDK Prerequisite Gate",
    "",
    "STOP. Do not use this SDK section yet unless you have already generated workflow code from the Quickstart-led "
    "CLI workflow.",
    "",
    "Before using any SDK link below, you must have a running CLI browser session, have explored the target page "
    "interactively, and have `notte sessions workflow-code` output to run, inspect, or refine. If you have not run "
    "`notte sessions workflow-code`, go back to https://docs.notte.cc/quickstart.md now.",
    "",
    "The SDK docs below are for generated-code editing and reference. They are not the starting point for manually "
    "authoring browser automation from scratch.",
    "",
]


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def fetch_openapi(url: str) -> dict:
    print(f"  fetching {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "notte-docs-llms-gen/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def render_openapi(spec: dict) -> list[str]:
    """Group operations by first tag, emit H2 per tag, bullet per operation."""
    by_tag: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in HTTP_METHODS:
                continue
            tags = op.get("tags") or ["misc"]
            tag = tags[0]
            op_id = op.get("operationId") or ""
            display = op.get("summary") or op_id or f"{method.upper()} {path}"
            desc = (op.get("description") or "").strip().split("\n")[0]
            by_tag[tag].append((method.upper(), display, desc, op_id))

    lines: list[str] = []
    for tag in sorted(by_tag):
        lines += [f"## {tag.title()}", ""]
        for method, display, desc, op_id in sorted(by_tag[tag], key=lambda x: x[1]):
            slug = slugify(op_id) if op_id else slugify(display)
            url = f"{SITE_URL}/api-reference/{slugify(tag)}/{slug}.md"
            line = f"- [{method} {display}]({url})"
            if desc:
                line += f": {desc}"
            lines.append(line)
        lines.append("")
    return lines


def read_frontmatter(page_path: str) -> dict:
    """Return parsed frontmatter dict for a nav page path."""
    for ext in (".mdx", ".md"):
        file = SRC_DIR / f"{page_path}{ext}"
        if file.exists():
            break
    else:
        print(f"  warning: no file for '{page_path}'", file=sys.stderr)
        return {}

    text = file.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}

    end = text.find("\n---", 3)
    if end == -1:
        return {}

    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as e:
        print(f"  warning: bad frontmatter in '{page_path}': {e}", file=sys.stderr)
        return {}


def page_url(page_path: str) -> str:
    return f"{SITE_URL}/{page_path}.md"


def render_page(page_path: str) -> str | None:
    fm = read_frontmatter(page_path)
    if fm.get("url"):
        return None
    title = str(fm.get("title", page_path))
    desc = str(fm.get("description", "")).strip()
    line = f"- [{title}]({page_url(page_path)})"
    if desc:
        line += f": {desc}"
    return line


def render_pages(pages: list, depth: int) -> list[str]:
    """Walk a pages array. Strings are pages; dicts are nested groups."""
    lines: list[str] = []
    heading = "#" * depth
    for entry in pages:
        if isinstance(entry, str):
            line = render_page(entry)
            if line is not None:
                lines.append(line)
        elif isinstance(entry, dict) and "group" in entry:
            lines.append("")
            lines.append(f"{heading} {entry['group']}")
            lines.append("")
            lines.extend(render_pages(entry.get("pages", []), depth + 1))
    return lines


def main() -> int:
    config = json.loads(DOCS_JSON.read_text())
    site_name = config.get("name", "Docs")

    intro = str(read_frontmatter("index").get("description", "")).strip()

    out: list[str] = [f"# {site_name}", ""]
    if intro:
        out += [f"> {intro}", ""]
    out += AGENT_READING_GUIDANCE

    languages = config.get("navigation", {}).get("languages", [])
    if not languages:
        print("error: no languages found in docs.json navigation", file=sys.stderr)
        return 1
    tabs = languages[0].get("tabs", [])
    for tab in tabs:
        out += ["", f"# {tab['tab']}", ""]
        if tab.get("tab") == "SDK":
            out += SDK_READING_GATE
        for group in tab.get("groups", []):
            out += [f"## {group['group']}", ""]
            out += render_pages(group.get("pages", []), depth=3)
            out += [""]
        if "openapi" in tab:
            try:
                spec = fetch_openapi(tab["openapi"])
                out += render_openapi(spec)
            except Exception as e:
                print(f"  warning: failed to fetch openapi {tab['openapi']}: {e}", file=sys.stderr)
                out += [f"- OpenAPI spec: {tab['openapi']}", ""]

    OUTPUT.write_text("\n".join(out).rstrip() + "\n")
    print(f"wrote {OUTPUT.relative_to(SRC_DIR.parent)} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
