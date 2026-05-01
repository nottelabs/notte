#!/usr/bin/env python3
"""
Verify that all MDX files match what their tester show= ranges produce.

For each changed MDX file:
1. Find the corresponding tester file
2. Extract the show= range
3. Generate what that range should produce
4. Compare with the actual MDX content
5. Report mismatches
"""

import re
import sys
import textwrap
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent  # docs/src
TESTERS_DIR = ROOT_DIR / "testers"
SNIPPETS_DIR = ROOT_DIR / "snippets"


def parse_magic_comments(content: str) -> tuple[dict[str, str], list[str]]:
    """Parse magic comments and return (config_dict, code_lines)."""
    config: dict[str, str] = {}
    lines = content.split("\n")
    code_start_idx = 0

    magic_pattern = re.compile(r"^#\s*@sniptest\s+(\w+)=(.+)$")

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped and code_start_idx == i:
            code_start_idx = i + 1
            continue
        match = magic_pattern.match(stripped)
        if match:
            key, value = match.groups()
            config[key.lower()] = value.strip()
            code_start_idx = i + 1
        else:
            break

    code_lines = lines[code_start_idx:]
    while code_lines and not code_lines[-1].strip():
        code_lines.pop()

    return config, code_lines


def get_show_range_output(code_lines: list[str], show_str: str) -> str:
    """Get what the show range produces after dedent."""
    if "-" in show_str:
        start, end = show_str.split("-", 1)
        start_idx = max(0, int(start.strip()) - 1)
        end_idx = min(len(code_lines), int(end.strip()))
    else:
        n = int(show_str.strip())
        start_idx = max(0, n - 1)
        end_idx = min(len(code_lines), n)

    selected = "\n".join(code_lines[start_idx:end_idx])
    return textwrap.dedent(selected).rstrip("\n")


def extract_code_from_mdx(mdx_path: Path) -> str | None:
    """Extract the code block content from an MDX file."""
    if not mdx_path.exists():
        return None
    content = mdx_path.read_text()
    match = re.search(r"```python[^\n]*\n(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).rstrip("\n")
    return None


def verify_mdx(mdx_path: Path) -> tuple[bool, str | None]:
    """Verify an MDX file matches its tester's show= range."""
    relative = mdx_path.relative_to(SNIPPETS_DIR)
    tester_path = TESTERS_DIR / relative.with_suffix(".py")

    if not tester_path.exists():
        return True, None  # No tester file, skip

    tester_content = tester_path.read_text()
    config, code_lines = parse_magic_comments(tester_content)

    if "show" not in config:
        return True, None  # No show directive, skip

    show_str = config["show"]
    generated = get_show_range_output(code_lines, show_str)

    mdx_code = extract_code_from_mdx(mdx_path)
    if mdx_code is None:
        return False, f"  [NO_CODE] {relative} - MDX has no code block"

    # Normalize for comparison
    gen_norm = "\n".join(line.rstrip() for line in generated.split("\n"))
    mdx_norm = "\n".join(line.rstrip() for line in mdx_code.split("\n"))

    if gen_norm == mdx_norm:
        return True, None

    # Check if it's just whitespace differences
    if gen_norm.strip() == mdx_norm.strip():
        return True, None

    # Detailed mismatch report
    gen_lines = len(generated.split("\n"))
    mdx_lines = len(mdx_code.split("\n"))

    return False, (
        f"  [MISMATCH] {relative}: show={show_str}\n"
        f"    Generated: {gen_lines} lines\n"
        f"    MDX: {mdx_lines} lines\n"
        f"    Generated preview: {generated[:100]}...\n"
        f"    MDX preview: {mdx_code[:100]}..."
    )


def main() -> None:
    # Get all changed MDX files from main
    import subprocess

    result = subprocess.run(
        ["git", "diff", "main", "--name-only", "--", "docs/src/snippets/"],
        cwd=ROOT_DIR.parent.parent,
        capture_output=True,
        text=True,
    )

    changed_mdx_files = [
        Path(ROOT_DIR.parent.parent) / line.strip()
        for line in result.stdout.split("\n")
        if line.strip().endswith(".mdx")
    ]

    print(f"Checking {len(changed_mdx_files)} changed MDX files...\n")

    issues: list[str] = []
    checked = 0

    for mdx_path in sorted(changed_mdx_files):
        if not mdx_path.exists():
            continue
        is_valid, message = verify_mdx(mdx_path)
        checked += 1
        if not is_valid and message:
            issues.append(message)

    print(f"Checked {checked} files")

    if issues:
        print("\nIssues found:\n")
        for issue in issues:
            print(issue)
        print(f"\nTotal issues: {len(issues)}")
        sys.exit(1)
    else:
        print("\nAll MDX files match their show= ranges!")
        sys.exit(0)


if __name__ == "__main__":
    main()
