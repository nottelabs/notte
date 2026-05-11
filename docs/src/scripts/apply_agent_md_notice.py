#!/usr/bin/env python3
"""Ensure agent-facing Markdown pages include the Notte skill/CLI notice.

Mintlify's global banner is part of the HTML chrome and is not emitted in
generated `.md` routes. This script inserts a shared `Visibility for="agents"`
snippet into every docs navigation page so AI assistants reading `.md` pages
see the same setup guidance.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parent.parent
DOCS_JSON = SRC_DIR / "docs.json"
SNIPPET_PATH = "/partials/agent-md-notice.mdx"
LEGACY_SNIPPET_PATHS = {"/snippets/agent-md-notice.mdx"}
IMPORT_LINE = f"import AgentMdNotice from '{SNIPPET_PATH}';"
COMPONENT_LINE = "<AgentMdNotice />"
SKIP_PAGES = {"index", "quickstart"}


def collect_pages(node: Any, pages: set[str]) -> None:
    if isinstance(node, str):
        pages.add(node)
        return
    if isinstance(node, list):
        for item in node:
            collect_pages(item, pages)
        return
    if not isinstance(node, dict):
        return

    for key in ("languages", "tabs", "groups", "versions", "pages"):
        collect_pages(node.get(key), pages)


def frontmatter_end(text: str) -> int:
    if not text.startswith("---\n"):
        return 0
    end = text.find("\n---\n", 4)
    if end == -1:
        return 0
    return end + len("\n---\n")


def frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    if end == -1:
        return ""
    return text[4:end]


def has_external_url_frontmatter(text: str) -> bool:
    return bool(re.search(r"(?m)^url:\s*", frontmatter(text)))


def split_import_block(text: str, start: int) -> tuple[str, str]:
    prefix = text[:start]
    rest = text[start:].lstrip("\n")
    imports: list[str] = []

    while True:
        match = re.match(r"import\s+[^\n]+\n", rest)
        if not match:
            break
        imports.append(match.group(0).rstrip())
        rest = rest[match.end() :].lstrip("\n")

    return prefix + "\n".join(imports), rest


def remove_notice(text: str) -> str:
    paths = {SNIPPET_PATH, *LEGACY_SNIPPET_PATHS}
    for path in paths:
        text = re.sub(rf"^import AgentMdNotice from ['\"]{re.escape(path)}['\"];\n*", "", text, flags=re.MULTILINE)
    text = re.sub(rf"\n*{re.escape(COMPONENT_LINE)}\n*", "\n", text)
    return text


def ensure_notice(text: str) -> str:
    text = remove_notice(text)

    start = frontmatter_end(text)
    import_block, body = split_import_block(text, start)

    if import_block.strip():
        import_block = import_block.rstrip() + "\n" + IMPORT_LINE
    else:
        import_block = text[:start].rstrip() + "\n" + IMPORT_LINE
        body = text[start:].lstrip("\n")

    return import_block.rstrip() + "\n\n" + COMPONENT_LINE + "\n\n" + body.lstrip("\n")


def navigation_mdx_pages() -> list[tuple[Path, bool]]:
    config = json.loads(DOCS_JSON.read_text(encoding="utf-8"))
    pages: set[str] = set()
    collect_pages(config.get("navigation"), pages)

    files: list[tuple[Path, bool]] = []
    for page in sorted(pages):
        file = SRC_DIR / f"{page}.mdx"
        if not file.exists():
            continue
        text = file.read_text(encoding="utf-8")
        should_include = page not in SKIP_PAGES and not has_external_url_frontmatter(text)
        files.append((file, should_include))
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if files need updates")
    args = parser.parse_args()

    changed: list[Path] = []
    for file, should_include in navigation_mdx_pages():
        original = file.read_text(encoding="utf-8")
        updated = ensure_notice(original) if should_include else remove_notice(original)
        if updated == original:
            continue
        changed.append(file)
        if not args.check:
            file.write_text(updated, encoding="utf-8")

    if changed:
        rel = [str(file.relative_to(SRC_DIR.parent.parent)) for file in changed]
        if args.check:
            print("agent md notice is missing or out of date in:")
            print("\n".join(rel))
            return 1
        print(f"updated {len(changed)} files")
        return 0

    print("agent md notice is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
