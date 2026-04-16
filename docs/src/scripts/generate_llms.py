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
    by_tag: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in HTTP_METHODS:
                continue
            tags = op.get("tags") or ["misc"]
            tag = tags[0]
            summary = op.get("summary") or op.get("operationId") or f"{method.upper()} {path}"
            desc = (op.get("description") or "").strip().split("\n")[0]
            by_tag[tag].append((method.upper(), summary, desc))

    lines: list[str] = []
    for tag in sorted(by_tag):
        lines += [f"## {tag.title()}", ""]
        for method, summary, desc in sorted(by_tag[tag], key=lambda x: x[1]):
            url = f"{SITE_URL}/api-reference/{tag}/{slugify(summary)}"
            line = f"- [{method} {summary}]({url})"
            if desc:
                line += f": {desc}"
            lines.append(line)
        lines.append("")
    return lines


def read_frontmatter(page_path: str) -> tuple[str, str]:
    """Return (title, description) for a nav page path."""
    for ext in (".mdx", ".md"):
        file = SRC_DIR / f"{page_path}{ext}"
        if file.exists():
            break
    else:
        print(f"  warning: no file for '{page_path}'", file=sys.stderr)
        return page_path, ""

    text = file.read_text()
    if not text.startswith("---"):
        return page_path, ""

    end = text.find("\n---", 3)
    if end == -1:
        return page_path, ""

    fm = yaml.safe_load(text[3:end]) or {}
    return str(fm.get("title", page_path)), str(fm.get("description", "")).strip()


def page_url(page_path: str) -> str:
    if page_path == "index":
        return f"{SITE_URL}/"
    return f"{SITE_URL}/{page_path}"


def render_page(page_path: str) -> str:
    title, desc = read_frontmatter(page_path)
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
            lines.append(render_page(entry))
        elif isinstance(entry, dict) and "group" in entry:
            lines.append("")
            lines.append(f"{heading} {entry['group']}")
            lines.append("")
            lines.extend(render_pages(entry.get("pages", []), depth + 1))
    return lines


def main() -> int:
    config = json.loads(DOCS_JSON.read_text())
    site_name = config.get("name", "Docs")

    _, intro = read_frontmatter("index")

    out: list[str] = [f"# {site_name}", ""]
    if intro:
        out += [f"> {intro}", ""]

    tabs = config["navigation"]["languages"][0]["tabs"]
    for tab in tabs:
        out += ["", f"# {tab['tab']}", ""]
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
