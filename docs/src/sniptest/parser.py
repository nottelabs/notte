#!/usr/bin/env python3
"""
Snippet Parser - Converts Python files with magic comments into Mintlify MDX snippets.

Magic comments (all work in markdown code blocks):
    # @sniptest language=python       - Language for syntax highlighting (default: python)
    # @sniptest filename=example.py   - Filename shown in code block header
    # @sniptest highlight=1,3,5-7     - Lines to highlight: {1,3,5-7}
    # @sniptest focus=1-5             - Lines to focus (dim others): focus={1-5}
    # @sniptest icon=rocket           - Icon in header: icon="rocket"
    # @sniptest lines=true            - Show line numbers
    # @sniptest wrap=true             - Wrap long lines
    # @sniptest expandable=true       - Make code block collapsible

Special (pre-processing, not passed to Mintlify):
    # @sniptest show=1-20             - Only include specific line range in output

Usage:
    python parser.py <input_file.py> [output_file.mdx]
    python parser.py testers/agents/fallback.py snippets/agents/fallback.mdx
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SnippetConfig:
    """Configuration parsed from magic comments."""

    language: str = "python"
    filename: str | None = None
    highlight: str | None = None
    focus: str | None = None
    icon: str | None = None
    lines: bool = False
    wrap: bool = False
    expandable: bool = False
    # Special (pre-processing only)
    show: tuple[int, int] | None = None


def parse_bool(value: str) -> bool:
    """Parse a boolean value from string."""
    return value.lower() in ("true", "1", "yes", "on")


def parse_magic_comments(content: str) -> tuple[SnippetConfig, str]:
    """
    Parse magic comments from the beginning of a Python file.

    Returns:
        tuple of (SnippetConfig, code_without_magic_comments)
    """
    config = SnippetConfig()
    lines = content.split("\n")
    code_start_idx = 0

    # Pattern to match: # @sniptest key=value
    magic_pattern = re.compile(r"^#\s*@sniptest\s+(\w+)=(.+)$")

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip empty lines at the start
        if not stripped and code_start_idx == i:
            code_start_idx = i + 1
            continue

        match = magic_pattern.match(stripped)
        if match:
            key, value = match.groups()
            key = key.lower()
            value = value.strip()

            if key == "language":
                config.language = value
            elif key == "filename":
                config.filename = value
            elif key == "highlight":
                config.highlight = value
            elif key == "focus":
                config.focus = value
            elif key == "icon":
                config.icon = value
            elif key == "lines":
                config.lines = parse_bool(value)
            elif key == "wrap":
                config.wrap = parse_bool(value)
            elif key == "expandable":
                config.expandable = parse_bool(value)
            elif key == "show":
                if "-" in value:
                    start, end = value.split("-", 1)
                    config.show = (int(start.strip()), int(end.strip()))
                else:
                    # Single number: show=5 means only line 5
                    n = int(value.strip())
                    config.show = (n, n)

            code_start_idx = i + 1
        else:
            # Non-magic comment line, stop parsing
            break

    # Get the code without magic comments
    code_lines = lines[code_start_idx:]

    # Remove trailing empty lines
    while code_lines and not code_lines[-1].strip():
        code_lines.pop()

    code = "\n".join(code_lines)

    return config, code


def apply_show_range(code: str, show_range: tuple[int, int] | None) -> str:
    """Apply the show range to extract only specific lines."""
    if show_range is None:
        return code

    start, end = show_range
    lines = code.split("\n")

    # Convert to 0-indexed
    start_idx = max(0, start - 1)
    end_idx = min(len(lines), end)

    return "\n".join(lines[start_idx:end_idx])


def parse_line_spec(spec: str) -> list[int]:
    """Parse a line spec like '1-3,5,7-9' into a list of line numbers."""
    result = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            result.extend(range(int(start.strip()), int(end.strip()) + 1))
        else:
            result.append(int(part))
    return sorted(set(result))


def remap_line_spec(spec: str, show_range: tuple[int, int]) -> str | None:
    """Remap line numbers based on show range.

    If show=3-5, then:
    - Original line 3 becomes output line 1
    - Original line 4 becomes output line 2
    - Lines outside 3-5 are removed

    Returns None if no lines remain after filtering.
    """
    show_start, show_end = show_range
    original_lines = parse_line_spec(spec)

    # Filter and remap
    remapped = []
    for line in original_lines:
        if show_start <= line <= show_end:
            # Remap: line 3 with show_start=3 becomes line 1
            new_line = line - show_start + 1
            remapped.append(new_line)

    if not remapped:
        return None

    # Convert back to spec format (compress consecutive ranges)
    return format_line_spec(remapped)


def format_line_spec(lines: list[int]) -> str:
    """Format a list of line numbers back into spec format like '1-3,5'."""
    if not lines:
        return ""

    lines = sorted(set(lines))
    ranges = []
    start = lines[0]
    end = lines[0]

    for line in lines[1:]:
        if line == end + 1:
            end = line
        else:
            ranges.append((start, end))
            start = line
            end = line
    ranges.append((start, end))

    parts = []
    for start, end in ranges:
        if start == end:
            parts.append(str(start))
        else:
            parts.append(f"{start}-{end}")

    return ",".join(parts)


def build_markdown_code_block(config: SnippetConfig, code: str) -> str:
    """Build a markdown code block (``` syntax)."""
    parts = [f"```{config.language}"]

    # Filename comes right after language
    if config.filename:
        parts.append(config.filename)

    # Boolean decorators
    if config.lines:
        parts.append("lines")
    if config.wrap:
        parts.append("wrap")
    if config.expandable:
        parts.append("expandable")

    # Icon with quotes
    if config.icon:
        parts.append(f'icon="{config.icon}"')

    # Line-based decorators
    if config.focus:
        parts.append(f"focus={{{config.focus}}}")
    if config.highlight:
        parts.append(f"highlight={{{config.highlight}}}")

    header = " ".join(parts)
    return f"{header}\n{code}\n```\n"


def generate_mdx(config: SnippetConfig, code: str) -> str:
    """Generate the MDX content for the snippet."""
    # If show is specified, remap highlight/focus line numbers
    if config.show:
        if config.highlight:
            config.highlight = remap_line_spec(config.highlight, config.show)
        if config.focus:
            config.focus = remap_line_spec(config.focus, config.show)
        code = apply_show_range(code, config.show)

    return build_markdown_code_block(config, code)


def parse_file(input_path: Path) -> tuple[SnippetConfig, str]:
    """Parse a Python file and return config and MDX content."""
    content = input_path.read_text()
    config, code = parse_magic_comments(content)
    mdx_content = generate_mdx(config, code)
    return config, mdx_content


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    config, mdx_content = parse_file(input_path)

    # Determine output path
    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        # Default: print to stdout
        print(mdx_content)
        return

    # Create parent directories if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    output_path.write_text(mdx_content)
    print(f"Generated: {output_path}")

    # Print summary
    print(f"  - Language: {config.language}")
    if config.filename:
        print(f"  - Filename: {config.filename}")
    if config.lines:
        print("  - Lines: true")
    if config.wrap:
        print("  - Wrap: true")
    if config.expandable:
        print("  - Expandable: true")
    if config.icon:
        print(f"  - Icon: {config.icon}")
    if config.focus:
        print(f"  - Focus: {config.focus}")
    if config.highlight:
        print(f"  - Highlight: {config.highlight}")
    if config.show:
        print(f"  - Show: lines {config.show[0]}-{config.show[1]} (pre-shaved)")


if __name__ == "__main__":
    main()
