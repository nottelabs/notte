#!/usr/bin/env python3
"""
Batch Snippet Processor - Converts all Python files in /testers to MDX snippets.

Crawls /testers/**/*.py and generates corresponding /snippets/**/*.mdx files
using the parser module.

Usage:
    python process.py                    # Process all files
    python process.py --dry-run          # Preview without writing
    python process.py --clean            # Remove orphaned .mdx files
    python process.py --verbose          # Show detailed output

Directory mapping:
    testers/agents/fallback.py  →  snippets/agents/fallback.mdx
    testers/sessions/basic.py   →  snippets/sessions/basic.mdx
"""

import argparse
import sys
from pathlib import Path

from parser import parse_file

# Resolve paths relative to this script
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent  # /docs/src
TESTERS_DIR = ROOT_DIR / "testers"
SNIPPETS_DIR = ROOT_DIR / "snippets"


# Header comment for generated files
def make_header(source: str) -> str:
    """Generate header comment for MDX file."""
    return f"{{/* Auto-generated mdx file. Do not edit! */}}\n{{/* @sniptest {source} */}}\n\n"


def get_output_path(input_path: Path) -> Path:
    """Convert a testers/ path to its corresponding snippets/ path."""
    relative = input_path.relative_to(TESTERS_DIR)
    return SNIPPETS_DIR / relative.with_suffix(".mdx")


def get_all_tester_files() -> list[Path]:
    """Find all Python files in the testers directory."""
    if not TESTERS_DIR.exists():
        return []
    return sorted(TESTERS_DIR.rglob("*.py"))


def get_all_generated_snippets() -> set[Path]:
    """Find all MDX files in snippets that could have been generated from testers."""
    generated = set()
    for tester_file in get_all_tester_files():
        generated.add(get_output_path(tester_file))
    return generated


def process_file(input_path: Path, dry_run: bool = False, verbose: bool = False) -> tuple[bool, str]:
    """
    Process a single tester file and generate its snippet.

    Returns:
        tuple of (success, message)
    """
    output_path = get_output_path(input_path)
    relative_input = input_path.relative_to(ROOT_DIR)
    relative_output = output_path.relative_to(ROOT_DIR)

    try:
        config, mdx_content = parse_file(input_path)

        # Add header comment with source file reference
        source_ref = str(input_path.relative_to(ROOT_DIR))
        full_content = make_header(source_ref) + mdx_content

        # Check if file needs updating
        if output_path.exists():
            existing = output_path.read_text()
            if existing == full_content:
                if verbose:
                    return True, f"  [unchanged] {relative_input}"
                return True, None

        if dry_run:
            return True, f"  [would create] {relative_output}"

        # Create parent directories and write file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_content)

        return True, f"  [generated] {relative_output}"

    except Exception as e:
        return False, f"  [error] {relative_input}: {e}"


def clean_orphaned_snippets(dry_run: bool = False, verbose: bool = False) -> list[str]:
    """
    Remove MDX snippets that no longer have a corresponding tester file.

    Returns:
        list of messages about removed files
    """
    messages = []

    # Find all MDX files in snippets directories that match tester structure
    for snippet_path in SNIPPETS_DIR.rglob("*.mdx"):
        # Check if this file has "@sniptest" header (was generated)
        try:
            content = snippet_path.read_text()
            if "@sniptest" not in content:
                continue  # Not a generated file, skip
        except Exception:
            continue

        # Check if corresponding tester exists
        relative = snippet_path.relative_to(SNIPPETS_DIR)
        tester_path = TESTERS_DIR / relative.with_suffix(".py")

        if not tester_path.exists():
            relative_snippet = snippet_path.relative_to(ROOT_DIR)
            if dry_run:
                messages.append(f"  [would remove] {relative_snippet}")
            else:
                snippet_path.unlink()
                messages.append(f"  [removed] {relative_snippet}")

    return messages


def main():
    argparser = argparse.ArgumentParser(
        description="Process tester files into MDX snippets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    argparser.add_argument("--dry-run", "-n", action="store_true", help="Preview changes without writing files")
    argparser.add_argument(
        "--clean", "-c", action="store_true", help="Remove orphaned snippets (generated files without testers)"
    )
    argparser.add_argument("--verbose", "-v", action="store_true", help="Show unchanged files")

    args = argparser.parse_args()

    # Validate directories
    if not TESTERS_DIR.exists():
        print(f"Error: Testers directory not found: {TESTERS_DIR}")
        print("Create the directory and add .py files to process.")
        sys.exit(1)

    tester_files = get_all_tester_files()

    if not tester_files:
        print(f"No Python files found in {TESTERS_DIR}")
        sys.exit(0)

    # Process files
    if args.dry_run:
        print("Dry run - no files will be written\n")

    print(f"Processing {len(tester_files)} tester file(s)...\n")

    success_count = 0
    error_count = 0
    messages = []

    for tester_file in tester_files:
        success, message = process_file(tester_file, dry_run=args.dry_run, verbose=args.verbose)
        if success:
            success_count += 1
        else:
            error_count += 1
        if message:
            messages.append(message)

    # Clean orphaned snippets if requested
    if args.clean:
        clean_messages = clean_orphaned_snippets(dry_run=args.dry_run, verbose=args.verbose)
        messages.extend(clean_messages)

    # Print messages
    for msg in messages:
        print(msg)

    # Summary
    print(f"\nProcessed: {success_count} | Errors: {error_count}")

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
