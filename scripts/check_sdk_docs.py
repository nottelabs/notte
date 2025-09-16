#!/usr/bin/env python3
"""
Pre-commit hook to check that SDK methods used in Python examples
are documented in the SDK Reference section of docs.json.

This script:
1. Scans Python files for method calls like `.method_name(`
2. Extracts the method names
3. Checks if each method has corresponding documentation in docs.json
4. Reports any missing documentation
"""

import json
import re
import sys
from pathlib import Path
from typing import Any


def extract_method_calls_from_file(file_path: Path) -> set[str]:
    """Extract method calls like .method_name( from a Python file."""
    method_calls: set[str] = set()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Pattern to match .method_name( - captures the method name
        pattern = r"\.(\w+)\("
        matches = re.findall(pattern, content)
        method_calls.update(matches)

    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")

    return method_calls


def get_documented_methods_from_docs_json(docs_json_path: Path) -> set[str]:
    """Extract documented method names from the SDK Reference section of docs.json."""
    documented_methods: set[str] = set()

    try:
        with open(docs_json_path, "r", encoding="utf-8") as f:
            docs_data = json.load(f)

        # Navigate to the SDK Reference section
        navigation = docs_data.get("navigation", {})
        tabs = navigation.get("tabs", [])

        for tab in tabs:
            if tab.get("tab") == "SDK Reference":
                groups = tab.get("groups", [])
                documented_methods.update(extract_methods_from_groups(groups))
                break

    except Exception as e:
        print(f"Error reading docs.json: {e}")
        sys.exit(1)

    return documented_methods


def extract_methods_from_groups(groups: list[dict[str, Any] | list[dict[str, Any]]]) -> set[str]:
    """Recursively extract method names from navigation groups."""
    methods: set[str] = set()

    for group in groups:
        if isinstance(group, dict):
            # Handle nested groups
            if "groups" in group:
                methods.update(extract_methods_from_groups(group["groups"]))

            # Handle pages
            if "pages" in group:
                for page in group["pages"]:
                    if isinstance(page, str):
                        # Extract method name from page path like "sdk-reference/remotesession/scrape"
                        parts = page.split("/")
                        if len(parts) >= 3 and parts[0] == "sdk-reference":
                            method_name = parts[-1]  # Last part is the method name
                            # Skip manual pages and index pages
                            if method_name not in ["manual", "index"]:
                                methods.add(method_name)
                    elif isinstance(page, dict) and "pages" in page:
                        # Handle nested groups within pages
                        methods.update(extract_methods_from_groups([page]))

    return methods


def find_python_files_to_check() -> list[Path]:
    """Find Python files that should be checked for SDK method usage."""
    python_files: list[Path] = []

    # Check examples directory
    examples_dir = Path("examples")
    if examples_dir.exists():
        python_files.extend(examples_dir.rglob("*.py"))

    # Check docs/src directory for Python snippets
    docs_src_dir = Path("docs/src")
    if docs_src_dir.exists():
        python_files.extend(docs_src_dir.rglob("*.py"))

    # Check packages/notte-sdk/src for usage examples
    sdk_src_dir = Path("packages/notte-sdk/src")
    if sdk_src_dir.exists():
        # Only check files that might contain usage examples, not the SDK implementation itself
        for py_file in sdk_src_dir.rglob("*.py"):
            # Skip __init__.py and implementation files, focus on client.py and similar
            if py_file.name in ["client.py", "endpoints.py"] or "example" in py_file.name.lower():
                python_files.append(py_file)

    return python_files


def find_mdx_files_to_check() -> list[Path]:
    """Find MDX files that may contain Python code fences."""
    mdx_files: list[Path] = []
    snippets_dir = Path("docs/src/snippets")
    if snippets_dir.exists():
        mdx_files.extend(snippets_dir.rglob("*.mdx"))
    return mdx_files


def extract_method_calls_from_mdx_file(file_path: Path) -> set[str]:
    """Extract method calls like .method_name( from Python code fences in an MDX file."""
    method_calls: set[str] = set()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Pattern to match Python code fences: ```python or ```python filename.py
        python_fence_pattern = r"```python(?:\s+\w+\.py)?\n(.*?)\n```"
        matches = re.findall(python_fence_pattern, content, re.DOTALL)

        for code_block in matches:
            # Extract method calls from each Python code block
            pattern = r"\.(\w+)\("
            code_matches = re.findall(pattern, code_block)
            method_calls.update(code_matches)

    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")

    return method_calls


def main():
    """Main function to run the SDK documentation check."""
    print("🔍 Checking SDK method documentation...")

    # Get all method calls from Python files
    all_method_calls: set[str] = set()
    python_files = find_python_files_to_check()
    mdx_files = find_mdx_files_to_check()

    print(f"📁 Scanning {len(python_files)} Python files...")

    for file_path in python_files:
        method_calls = extract_method_calls_from_file(file_path)
        all_method_calls.update(method_calls)
        if method_calls:
            print(f"  📄 {file_path}: {sorted(method_calls)}")

    print(f"📁 Scanning {len(mdx_files)} MDX files for Python code fences...")

    for file_path in mdx_files:
        method_calls = extract_method_calls_from_mdx_file(file_path)
        all_method_calls.update(method_calls)
        if method_calls:
            print(f"  📄 {file_path}: {sorted(method_calls)}")

    # Get documented methods from docs.json
    docs_json_path = Path("docs/src/docs.json")
    if not docs_json_path.exists():
        print(f"❌ Error: {docs_json_path} not found")
        sys.exit(1)

    documented_methods = get_documented_methods_from_docs_json(docs_json_path)
    print(f"📚 Found {len(documented_methods)} documented methods in SDK Reference")

    # Filter method calls to only include SDK-related methods
    # Common SDK method patterns
    sdk_methods = {
        "scrape",
        "observe",
        "execute",
        "start",
        "stop",
        "run",
        "status",
        "replay",
        "cdp_url",
        "set_cookies",
        "get_cookies",
        "viewer_browser",
        "viewer_cdp",
        "viewer",
        "offset",
        "debug_info",
        "debug_tab_info",
        "add_credentials",
        "get_credentials",
        "delete_credentials",
        "list_credentials",
        "set_credit_card",
        "get_credit_card",
        "delete_credit_card",
        "generate_password",
        "create_number",
        "delete_number",
        "emails",
        "sms",
        "delete",
        "download",
        "upload",
        "list_downloaded_files",
        "list_uploaded_files",
        "update",
        "fork",
        "get_curl",
        "health_check",
    }

    # Filter to only SDK methods
    sdk_method_calls = all_method_calls.intersection(sdk_methods)

    print(f"🎯 Found {len(sdk_method_calls)} SDK method calls: {sorted(sdk_method_calls)}")

    # Check for missing documentation
    missing_docs = sdk_method_calls - documented_methods

    if missing_docs:
        print(f"\n❌ Missing documentation for {len(missing_docs)} SDK methods:")
        for method in sorted(missing_docs):
            # Find which files contain this method
            files_with_method: list[str] = []
            for file_path in python_files:
                method_calls = extract_method_calls_from_file(file_path)
                if method in method_calls:
                    files_with_method.append(str(file_path))
            for file_path in mdx_files:
                method_calls = extract_method_calls_from_mdx_file(file_path)
                if method in method_calls:
                    files_with_method.append(str(file_path))

            print(f"  - {method}")
            for file_path in files_with_method:
                print(f"    📍 Found in: {file_path}")
        print("\n💡 Add documentation for these methods in docs/src/sdk-reference/")
        sys.exit(1)
    else:
        print("\n✅ All SDK methods are documented!")
        sys.exit(0)


if __name__ == "__main__":
    main()
