#!/usr/bin/env python3
"""Generate the CLI reference from the notte-cli submodule.

The pages under `cli-reference/` are written by notte-cli's own generator
(`scripts/gendocs`), which walks the CLI's command tree, so they cannot drift
from the pinned CLI. This script runs it, replaces `cli-reference/`, and keeps
the "CLI" tab in `docs.json` listing exactly the generated pages.
Since `llms.txt` is built from the sidebar, a regeneration rebuilds it too.

    python docs/src/scripts/generate_cli_reference.py          # regenerate
    python docs/src/scripts/generate_cli_reference.py --check  # fail if stale

Requires Go, uv, and an initialized notte-cli submodule.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from apply_agent_md_notice import ensure_notice

SRC_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SRC_DIR.parent.parent
CLI_DIR = REPO_ROOT / "notte-cli"
OUT_DIR = SRC_DIR / "cli-reference"
DOCS_JSON = SRC_DIR / "docs.json"
TAB = "CLI"
# The CLI tab sits right after this one.
AFTER_TAB = "APIs and SDKs"
GENERATE_TIMEOUT_SECONDS = 600
SESSION_COMPATIBILITY_NOTE = (
    "<Note>\n"
    "  Hosted sessions use Notte-managed Chromium. Browser-type flags and their legacy aliases are accepted for "
    "compatibility; they do not select a different hosted browser build. "
    "See [Session configuration](/sdk-reference/manual/session) for supported settings.\n"
    "</Note>\n"
)


def prepare_page(name: str, text: str) -> str:
    text = ensure_notice(text.rstrip("\n") + "\n")
    if name == "sessions" and SESSION_COMPATIBILITY_NOTE not in text:
        text = text.replace("<AgentMdNotice />\n", "<AgentMdNotice />\n\n" + SESSION_COMPATIBILITY_NOTE, 1)
    return text


def generate(out: Path) -> None:
    if not (CLI_DIR / "go.mod").exists():
        sys.exit("notte-cli submodule is not initialized: run `git submodule update --init notte-cli`")
    try:
        subprocess.run(
            ["go", "run", "./scripts/gendocs", "-out", str(out)],
            cwd=CLI_DIR,
            check=True,
            timeout=GENERATE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        sys.exit(f"notte-cli's generator did not finish within {GENERATE_TIMEOUT_SECONDS}s")
    # Match what the repository's hooks would do to the pages: add the agent
    # notice every sidebar page carries, and end with one newline.
    for page in out.glob("*.mdx"):
        page.write_text(prepare_page(page.stem, normalize_icons(page.read_text())))


def normalize_icons(text: str) -> str:
    # The submodule owns commands; the docs site owns product presentation.
    for title, icon in (("Functions", "flower"), ("Sessions", "tv")):
        text = re.sub(r'<Card icon="[^"]+" title="' + title + r'"', f'<Card icon="{icon}" title="{title}"', text)
    return text


def cli_llms_matches(fresh: Path, existing: str) -> bool:
    expected = []
    for name in nav_pages(fresh):
        text = (fresh / (name.split("/")[-1] + ".mdx")).read_text()
        # gendocs emits JSON-quoted YAML strings; decode escapes, not display quotes.
        fields = {}
        for field in ("title", "description"):
            match = re.search(r"^" + field + r": (.+)$", text, re.MULTILINE)
            if match is None:
                return False
            fields[field] = json.loads(match.group(1))
        expected.append(f"- [{fields['title']}](https://docs.notte.cc/{name}.md): {fields['description']}")
    actual = [line for line in existing.splitlines() if "](https://docs.notte.cc/cli-reference/" in line]
    return actual == expected


def nav_pages(out: Path) -> list[str]:
    names = sorted(p.stem for p in out.glob("*.mdx"))
    # Overview first, the catch-all page last, groups alphabetically between.
    names.sort(key=lambda n: (n != "index", n == "other", n))
    return [f"cli-reference/{n}" for n in names]


def sync_nav(docs: dict[str, Any], pages: list[str]) -> None:
    overview, commands = pages[:1], pages[1:]
    entry = {
        "tab": TAB,
        "groups": [
            {"group": "Getting Started", "pages": overview},
            {"group": "Commands", "pages": commands},
        ],
    }
    tabs: list[dict[str, Any]] = docs["navigation"]["tabs"]
    for i, t in enumerate(tabs):
        if t.get("tab") == TAB:
            tabs[i] = entry
            return
    after = next(i for i, t in enumerate(tabs) if t.get("tab") == AFTER_TAB)
    tabs.insert(after + 1, entry)


def same_tree(a: Path, b: Path) -> bool:
    names_a = sorted(p.name for p in a.glob("*.mdx")) if a.exists() else []
    names_b = sorted(p.name for p in b.glob("*.mdx"))
    if names_a != names_b:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, names_b, shallow=False)
    return not mismatch and not errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail instead of writing when out of date")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        generate(fresh)
        pages = nav_pages(fresh)

        current = DOCS_JSON.read_text()
        docs = json.loads(current)
        sync_nav(docs, pages)
        updated = json.dumps(docs, indent=2, ensure_ascii=False) + "\n"

        if args.check:
            stale = []
            if not same_tree(OUT_DIR, fresh):
                stale.append("docs/src/cli-reference/")
            if json.loads(current) != docs:
                stale.append("docs/src/docs.json (CLI tab)")
            llms_path = DOCS_JSON.with_name("llms.txt")
            if not llms_path.exists() or not cli_llms_matches(fresh, llms_path.read_text()):
                stale.append("docs/src/llms.txt (CLI entries)")
            if stale:
                print(
                    "CLI reference is out of date with the notte-cli submodule: "
                    + ", ".join(stale)
                    + ".\nRun `python docs/src/scripts/generate_cli_reference.py` and commit the result.",
                    file=sys.stderr,
                )
                return 1
            print("CLI reference is up to date.")
            return 0

        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)
        shutil.copytree(fresh, OUT_DIR)
        if updated != current:
            DOCS_JSON.write_text(updated)
    # llms.txt lists every page's title and description, so it is rebuilt even
    # when the navigation is unchanged.
    try:
        subprocess.run(
            ["uv", "run", "python", "scripts/generate_llms.py"],
            cwd=SRC_DIR,
            check=True,
            timeout=GENERATE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        sys.exit(f"generate_llms.py did not finish within {GENERATE_TIMEOUT_SECONDS}s")
    print(f"Wrote {len(pages)} pages to docs/src/cli-reference/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
