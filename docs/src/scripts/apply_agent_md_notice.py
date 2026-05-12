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
SDK_REFERENCE_PREFIX = "/sdk-reference/"
INLINE_VISIBILITY_RE = re.compile(
    r'<Visibility for="humans">(?P<human>[^<]*?/sdk-reference/[^<]*?)</Visibility>'
    r'<Visibility for="agents">(?P<agent>[^<]*?/sdk-reference/[^<]*?)</Visibility>'
)
MARKDOWN_LINK_RE = re.compile(
    r"(?P<link>\[(?!\[)(?:`[^`]+`|[^\]\n`\[]+)\]\((?P<href>/sdk-reference/[^)\s#]+)(?P<anchor>#[^)]+)?\))"
)
WRAPPED_SDK_CARD_RE = re.compile(
    r'(?ms)^(?P<indent>[ \t]*)<Visibility for="humans">\n'
    r"(?P<human>.*?\n(?P=indent)[ \t]*</Card>)\n"
    r"(?P=indent)</Visibility>\n"
    r'(?P=indent)<Visibility for="agents">\n'
    r".*?\n(?P=indent)[ \t]*</Card>\n"
    r"(?P=indent)</Visibility>"
)
SDK_CARD_RE = re.compile(r"(?ms)^(?P<indent>[ \t]*)<Card\n(?P<body>.*?\n(?P=indent)</Card>)")


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


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.rstrip("\n") + "\n"


def sdk_agent_href(href: str) -> str:
    if href.endswith(".md"):
        return href
    return f"{href}.md"


def shift_block(text: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" if line else line for line in text.splitlines())


def unindent_visibility_child(text: str, parent_indent: str) -> str:
    child_indent = f"{parent_indent}  "
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith(child_indent):
            lines.append(f"{parent_indent}{line[len(child_indent) :]}")
        else:
            lines.append(line)
    return "\n".join(lines)


def normalize_card_text_indentation(card: str, card_indent: str) -> str:
    lines = card.splitlines()
    in_text = False
    normalized: list[str] = []
    text_indent = f"{card_indent}  "

    for line in lines:
        stripped = line.strip()
        if stripped == ">":
            in_text = True
            normalized.append(line)
            continue
        if stripped == "</Card>":
            in_text = False
            normalized.append(line)
            continue
        if in_text and stripped and not line.startswith(text_indent):
            normalized.append(f"{text_indent}{line.lstrip()}")
            continue
        normalized.append(line)

    return "\n".join(normalized)


def normalize_sdk_visibility_wrappers(text: str) -> str:
    def unwrap_card(match: re.Match[str]) -> str:
        return unindent_visibility_child(match.group("human"), match.group("indent"))

    text = WRAPPED_SDK_CARD_RE.sub(unwrap_card, text)
    return INLINE_VISIBILITY_RE.sub(lambda match: match.group("human"), text)


def wrap_sdk_markdown_links(text: str) -> str:
    def replace_link(match: re.Match[str]) -> str:
        href = match.group("href")
        if href.endswith(".md"):
            return match.group(0)

        human_link = match.group("link")
        agent_href = sdk_agent_href(href)
        agent_link = human_link.replace(f"({href}", f"({agent_href}", 1)
        return f'<Visibility for="humans">{human_link}</Visibility><Visibility for="agents">{agent_link}</Visibility>'

    return MARKDOWN_LINK_RE.sub(replace_link, text)


def wrap_sdk_cards(text: str) -> str:
    def replace_card(match: re.Match[str]) -> str:
        indent = match.group("indent")
        card = normalize_card_text_indentation(match.group(0), indent)
        if f'href="{SDK_REFERENCE_PREFIX}' not in card or ".md" in card:
            return card

        agent_card = re.sub(
            rf'href="({re.escape(SDK_REFERENCE_PREFIX)}[^"#]+)"',
            lambda href_match: f'href="{sdk_agent_href(href_match.group(1))}"',
            card,
            count=1,
        )
        return "\n".join(
            [
                f'{indent}<Visibility for="humans">',
                shift_block(card, "  "),
                f"{indent}</Visibility>",
                f'{indent}<Visibility for="agents">',
                shift_block(agent_card, "  "),
                f"{indent}</Visibility>",
            ]
        )

    return SDK_CARD_RE.sub(replace_card, text)


def ensure_sdk_agent_links(text: str) -> str:
    text = normalize_sdk_visibility_wrappers(text)
    text = wrap_sdk_markdown_links(text)
    return wrap_sdk_cards(text)


def ensure_notice(text: str) -> str:
    text = remove_notice(text)

    start = frontmatter_end(text)
    import_block, body = split_import_block(text, start)

    if import_block.strip():
        import_block = import_block.rstrip() + "\n" + IMPORT_LINE
    else:
        import_block = text[:start].rstrip() + "\n" + IMPORT_LINE
        body = text[start:].lstrip("\n")

    return normalize_whitespace(import_block.rstrip() + "\n\n" + COMPONENT_LINE + "\n\n" + body.lstrip("\n"))


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


def sdk_reference_pages() -> list[Path]:
    sdk_reference_dir = SRC_DIR / "sdk-reference"
    if not sdk_reference_dir.exists():
        return []
    return sorted(sdk_reference_dir.rglob("*.mdx"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if files need updates")
    args = parser.parse_args()

    updates: dict[Path, str] = {}
    changed: list[Path] = []
    for file, should_include in navigation_mdx_pages():
        original = file.read_text(encoding="utf-8")
        updated = ensure_notice(original) if should_include else normalize_whitespace(remove_notice(original))
        updates[file] = updated

    for file in sdk_reference_pages():
        text = updates.get(file, file.read_text(encoding="utf-8"))
        updates[file] = normalize_whitespace(ensure_sdk_agent_links(text))

    for file, updated in updates.items():
        original = file.read_text(encoding="utf-8")
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
