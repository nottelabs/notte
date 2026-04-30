#!/usr/bin/env python3
"""One-shot preprocessor that wraps internal links in hand-authored MDX with
<Visibility for="humans">/<Visibility for="agents"> pairs so the .md export
emits .md-suffixed hrefs while the HTML render is unchanged.

Scope: hand-authored MDX under docs/src. Skips sdk-reference/ (sphinx_mintlify
auto-gen, handled separately) and snippets/ (sniptest auto-gen). Also skips
any file starting with the sniptest auto-gen marker as a safety belt.

Transforms:
  - Inline markdown links: [text](/path) -> <Visibility for="humans">[text](/path)</Visibility>
                                            <Visibility for="agents">[text](/path.md)</Visibility>
  - JSX Card components:   <Card ... href="/path" ...>...</Card> -> wrapped pair, agent variant gets .md href.

Skips:
  - External URLs (http://, https://, mailto:, tel:)
  - Anchor-only links (#foo)
  - Links inside fenced code blocks
  - Links/cards already wrapped in <Visibility>

Usage:
    python docs/src/scripts/wrap_md_links.py --dry-run   # preview diff stats
    python docs/src/scripts/wrap_md_links.py             # write in place
    python docs/src/scripts/wrap_md_links.py --path foo.mdx  # single file
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # docs/src

EXCLUDE_DIR_NAMES = {"sdk-reference", "snippets", "images", "logo", "sniptest", "testers", "tests", "scripts"}
AUTO_GEN_MARKER = "{/* Auto-generated mdx file. Do not edit! */}"

VIS_HUMANS_OPEN = '<Visibility for="humans">'
VIS_AGENTS_OPEN = '<Visibility for="agents">'
VIS_CLOSE = "</Visibility>"

INLINE_LINK_RE = re.compile(r"\[(?P<text>[^\]\n]+)\]\((?P<path>/[^)\s]*)\)")
CARD_OPEN_RE = re.compile(r'<Card\b[^>]*?\shref="(?P<path>/[^"]+)"[^>]*>')
VIS_OPEN_RE = re.compile(r'<Visibility\s+for="[^"]+"\s*>')


def is_external(path: str) -> bool:
    return "://" in path or path.startswith(("mailto:", "tel:", "#"))


def add_md_suffix(path: str) -> str:
    """Insert .md before any anchor or query string."""
    rest, anchor = (path.split("#", 1) + [""])[:2]
    rest, query = (rest.split("?", 1) + [""])[:2]
    if rest.endswith(".md"):
        return path
    out = rest + ".md"
    if query:
        out += "?" + query
    if anchor:
        out += "#" + anchor
    return out


def find_code_regions(text: str) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    in_fence = False
    fence_start = 0
    pos = 0
    for line in text.split("\n"):
        line_end = pos + len(line) + 1
        if line.lstrip().startswith("```"):
            if not in_fence:
                in_fence = True
                fence_start = pos
            else:
                regions.append((fence_start, line_end))
                in_fence = False
        pos = line_end
    if in_fence:
        regions.append((fence_start, pos))
    return regions


def find_visibility_regions(text: str) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    pos = 0
    while True:
        m = VIS_OPEN_RE.search(text, pos)
        if not m:
            break
        end_idx = text.find(VIS_CLOSE, m.end())
        if end_idx == -1:
            break
        regions.append((m.start(), end_idx + len(VIS_CLOSE)))
        pos = end_idx + len(VIS_CLOSE)
    return regions


def in_any_region(idx: int, regions: list[tuple[int, int]]) -> bool:
    return any(s <= idx < e for s, e in regions)


def transform_inline_links(text: str) -> tuple[str, int]:
    code_regions = find_code_regions(text)
    vis_regions = find_visibility_regions(text)
    out: list[str] = []
    last = 0
    count = 0
    for m in INLINE_LINK_RE.finditer(text):
        idx = m.start()
        if in_any_region(idx, code_regions) or in_any_region(idx, vis_regions):
            continue
        path = m.group("path")
        if is_external(path):
            continue
        text_part = m.group("text")
        md_path = add_md_suffix(path)
        replacement = (
            f"{VIS_HUMANS_OPEN}[{text_part}]({path}){VIS_CLOSE}{VIS_AGENTS_OPEN}[{text_part}]({md_path}){VIS_CLOSE}"
        )
        out.append(text[last:idx])
        out.append(replacement)
        last = m.end()
        count += 1
    out.append(text[last:])
    return "".join(out), count


def find_matching_card_close(text: str, after: int) -> int:
    """Return the start index of the </Card> that closes the open at `after`.
    Returns -1 if there's a nested <Card before that close (signal: skip)."""
    close_idx = text.find("</Card>", after)
    if close_idx == -1:
        return -1
    # Reject nested Cards (none expected in this corpus, but be safe).
    if re.search(r"<Card\b", text[after:close_idx]):
        return -1
    return close_idx


def reindent_block(block: str, base_indent: str) -> str:
    """Re-indent a Card block so it sits one level deeper than `base_indent`.
    First line gets `base_indent + "  "`; subsequent lines get +2 added to the
    indent they already had."""
    inner = base_indent + "  "
    lines = block.split("\n")
    out = [inner + lines[0]]
    for ln in lines[1:]:
        out.append("  " + ln)
    return "\n".join(out)


def transform_cards(text: str) -> tuple[str, int]:
    code_regions = find_code_regions(text)
    vis_regions = find_visibility_regions(text)
    matches = list(CARD_OPEN_RE.finditer(text))
    matches.reverse()  # transform end-to-start so earlier offsets stay valid
    new = text
    count = 0
    for m in matches:
        open_start = m.start()
        if in_any_region(open_start, code_regions) or in_any_region(open_start, vis_regions):
            continue
        path = m.group("path")
        if is_external(path):
            continue
        close_start = find_matching_card_close(new, m.end())
        if close_start == -1:
            continue
        close_end = close_start + len("</Card>")
        block = new[open_start:close_end]
        # Determine the file indent of the <Card> line.
        line_start = new.rfind("\n", 0, open_start) + 1
        indent = new[line_start:open_start]
        if indent.strip():
            # Card open isn't at the start of a (whitespace-only) prefix; bail.
            continue

        md_path = add_md_suffix(path)
        agent_block = block.replace(f'href="{path}"', f'href="{md_path}"', 1)
        human_indented = reindent_block(block, indent)
        agent_indented = reindent_block(agent_block, indent)
        replacement = (
            f"{VIS_HUMANS_OPEN}\n"
            f"{human_indented}\n"
            f"{indent}{VIS_CLOSE}\n"
            f"{indent}{VIS_AGENTS_OPEN}\n"
            f"{agent_indented}\n"
            f"{indent}{VIS_CLOSE}"
        )
        new = new[:open_start] + replacement + new[close_end:]
        count += 1
    return new, count


def is_in_scope(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIR_NAMES for part in rel.parts):
        return False
    return True


def is_auto_generated(content: str) -> bool:
    return content.lstrip().startswith(AUTO_GEN_MARKER)


def process_file(path: Path, *, dry_run: bool) -> tuple[int, int]:
    content = path.read_text()
    if is_auto_generated(content):
        return 0, 0
    new, n_links = transform_inline_links(content)
    new, n_cards = transform_cards(new)
    if (n_links or n_cards) and not dry_run and new != content:
        path.write_text(new)
    return n_links, n_cards


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="don't write files")
    p.add_argument("--path", help="process a single file (relative to docs/src)")
    args = p.parse_args()

    if args.path:
        targets = [ROOT / args.path]
    else:
        targets = [p for p in ROOT.rglob("*.mdx") if is_in_scope(p)]

    total_links = 0
    total_cards = 0
    files_changed = 0
    for f in sorted(targets):
        n_links, n_cards = process_file(f, dry_run=args.dry_run)
        if n_links or n_cards:
            files_changed += 1
            rel = f.relative_to(ROOT)
            print(f"  {rel}: {n_links} links, {n_cards} cards")
        total_links += n_links
        total_cards += n_cards

    verb = "would change" if args.dry_run else "changed"
    print(f"\n{files_changed} file(s) {verb} | {total_links} inline links, {total_cards} cards wrapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
