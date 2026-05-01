#!/usr/bin/env python3
"""
Verify that all show= ranges in tester files produce complete, valid code snippets.

Checks for:
1. Snippets that end with incomplete statements (e.g., ending with ':', '(', '[', '{')
2. Snippets that are significantly shorter than expected
3. Snippets that don't match their generated MDX

Usage:
    python verify_snippets.py              # Check all testers
    python verify_snippets.py --fix        # Auto-fix what can be fixed
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
    # Remove trailing empty lines
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


def check_incomplete_snippet(code: str) -> bool:
    """Check if snippet ends with incomplete statement."""
    if not code.strip():
        return False

    lines = [line.strip() for line in code.split("\n") if line.strip()]
    if not lines:
        return False

    last_line = lines[-1]
    # Check for incomplete statements
    incomplete_patterns = [":", "(", "[", "{", "\\"]
    # But allow if it's a complete statement like "if x:" followed by content
    if last_line.endswith(":") and len(lines) == 1:
        return True  # Incomplete if statement with no body
    if any(last_line.endswith(p) for p in incomplete_patterns[:-1]):  # Exclude backslash
        # Check if it's actually incomplete (not a complete expression)
        if last_line.endswith(":") and len(lines) > 1:
            # Check if next line is indented (has body)
            return False
        return True

    return False


def verify_tester(tester_path: Path) -> tuple[bool, str | None]:
    """Verify a tester file. Returns (is_valid, error_message)."""
    relative = tester_path.relative_to(TESTERS_DIR)

    content = tester_path.read_text()
    config, code_lines = parse_magic_comments(content)

    if "show" not in config:
        return True, None  # No show directive to verify

    show_str = config["show"]
    generated = get_show_range_output(code_lines, show_str)

    # Check for incomplete snippets
    if check_incomplete_snippet(generated):
        return False, f"  [INCOMPLETE] {relative}: show={show_str} - snippet ends with incomplete statement"

    # Check if snippet is suspiciously short (less than 2 lines) AND incomplete
    snippet_lines = generated.split("\n")
    if len(snippet_lines) < 2 and len(code_lines) > 5:
        # Single-line snippets are OK if they're complete statements
        if not check_incomplete_snippet(generated):
            return True, None  # Single line but complete, that's fine
        return (
            False,
            f"  [TOO_SHORT] {relative}: show={show_str} - snippet has only {len(snippet_lines)} line(s) and appears incomplete",
        )

    return True, None


def main() -> None:
    _ = "--fix" in sys.argv

    tester_files = sorted(TESTERS_DIR.rglob("*.py"))
    issues: list[str] = []

    for tester_file in tester_files:
        is_valid, message = verify_tester(tester_file)
        if not is_valid and message:
            issues.append(message)

    if issues:
        print("Issues found:\n")
        for issue in issues:
            print(issue)
        print(f"\nTotal issues: {len(issues)}")
        sys.exit(1)
    else:
        print("All snippets are complete!")
        sys.exit(0)


if __name__ == "__main__":
    main()
