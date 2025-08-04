import asyncio
import datetime as dt
import email
import http.server
import json
import mimetypes
import os
import re
import socket
import socketserver
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final, Literal
from urllib.parse import ParseResult, parse_qs, quote, urlencode, urlparse

import pytest
from loguru import logger
from mhtml_converter import convert_mhtml
from notte_core import __version__
from notte_core.actions import InteractionAction
from notte_core.browser.observation import Observation
from pydantic import BaseModel, Field

import notte

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
DOM_REPORTS_DIR: Final[Path] = Path(__file__).parent / ".dom_reports"
DATE_STR = dt.datetime.now().strftime("%Y-%m-%d")
SNAPSHOT_DIR_STATIC: Final[Path] = DOM_REPORTS_DIR / Path("static_" + DATE_STR)
SNAPSHOT_DIR_LIVE: Final[Path] = DOM_REPORTS_DIR / Path("live_" + DATE_STR)
SNAPSHOT_DIR_LOCAL: Final[Path] = DOM_REPORTS_DIR / Path("local_" + DATE_STR)
SNAPSHOT_DIR_REPLAY: Final[Path] = DOM_REPORTS_DIR / Path("replay_" + DATE_STR)
SNAPSHOT_DIR_TRAJECTORY: Final[Path] = DOM_REPORTS_DIR / Path("trajectory_" + DATE_STR)


def get_last_static_snapshot_dir() -> Path:
    return sorted(DOM_REPORTS_DIR.glob("static_*"))[-1]


# -----------------------------------------------------------------------------
# Local Server for saved snapshots
# -----------------------------------------------------------------------------


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class LocalServer:
    def __init__(self, port: int = 8000, directory: str | Path | None = None):
        self.port = port
        self.directory = directory or os.getcwd()
        self.original_dir = os.getcwd()
        self.httpd = None
        self.server_thread = None

    def start(self):
        # Change to the HTML file directory
        os.chdir(self.directory)

        Handler = http.server.SimpleHTTPRequestHandler
        self.httpd = socketserver.TCPServer(("", self.port), Handler)

        # Start server in background thread
        self.server_thread = threading.Thread(target=self.httpd.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        print(f"Server started on http://localhost:{self.port}")

    def stop(self):
        os.chdir(self.original_dir)

        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()

        if self.server_thread:
            self.server_thread.join(timeout=1)

        print("Server stopped")


# -----------------------------------------------------------------------------
# MHTML conversion helpers
# -----------------------------------------------------------------------------


def remove_base_tags(html_file_path: str | Path, output_file_path: str | Path | None = None) -> None:
    """
    Remove all base tags from HTML file
    """

    with open(html_file_path, "r", encoding="utf-8") as file:
        content = file.read()

    # Remove all base tags
    content = re.sub(r"<base[^>]*>", "", content, flags=re.IGNORECASE)

    output_path = output_file_path or html_file_path

    with open(output_path, "w", encoding="utf-8") as file:
        file.write(content)


def comprehensive_relative_path_fix(html_file_path, output_file_path=None):
    """
    More comprehensive fix for all types of resource references
    """

    with open(html_file_path, "r", encoding="utf-8") as file:
        content = file.read()

    # List of all possible HTML attributes that might contain resource paths
    attributes = [
        "src",
        "href",
        "action",
        "content",
        "data",
        "value",
        "poster",
        "background",
        "cite",
        "formaction",
        "icon",
        "manifest",
        "ping",
    ]

    # Fix quoted attributes
    for attr in attributes:
        # Double quotes
        pattern = f'{attr}\\s*=\\s*"[^"]*?(page_files[^"]*)"'
        replacement = f'{attr}="./\\1"'
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

        # Single quotes
        pattern = f"{attr}\\s*=\\s*'[^']*?(page_files[^']*)'"
        replacement = f"{attr}='./\\1'"
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

    # Fix CSS url() references (various formats)
    css_patterns = [
        r'url\(\s*"[^"]*?(page_files[^"]*)"\s*\)',  # url("path")
        r"url\(\s*'[^']*?(page_files[^']*)'\s*\)",  # url('path')
        r"url\(\s*[^)]*?(page_files[^)]*)\s*\)",  # url(path)
    ]

    for pattern in css_patterns:
        content = re.sub(pattern, r"url(./\1)", content)

    # Fix @import statements
    import_patterns = [
        r'@import\s+"[^"]*?(page_files[^"]*)"',  # @import "path"
        r"@import\s+'[^']*?(page_files[^']*)'",  # @import 'path'
        r"@import\s+url\([^)]*?(page_files[^)]*)\)",  # @import url(path)
    ]

    for pattern in import_patterns:
        content = re.sub(pattern, r'@import "./\1"', content)

    # Handle inline style attributes
    style_pattern = r'style\s*=\s*"([^"]*?)[^"]*?(page_files[^"]*?)([^"]*?)"'

    def style_replacer(match):
        before, path, after = match.groups()
        return f'style="{before}./page_files{path.split("page_files", 1)[1]}{after}"'

    content = re.sub(style_pattern, style_replacer, content)

    output_path = output_file_path or html_file_path

    with open(output_path, "w", encoding="utf-8") as file:
        file.write(content)


def parse_mhtml_content_mapping(mhtml_file):
    """
    Parse the original MHTML file to create a mapping from Content-IDs to filenames.
    This replicates the logic from the Go script to determine how files were named.
    """
    content_id_to_file = {}
    content_location_to_file = {}

    with open(mhtml_file, "rb") as f:
        # Parse as email message (MHTML is based on MIME)
        msg = email.message_from_bytes(f.read())

    # Counter for sequential numbering (matching Go script logic)
    part_index = 1
    base_name = Path(mhtml_file).stem
    save_dir = f"{base_name}_files"

    def process_part(part, index):
        """Process a single MIME part and determine its filename."""
        content_type = part.get_content_type()

        if not content_type:
            return None, None, None

        # Skip the main HTML part (first text/html part)
        if content_type == "text/html" and index == 0:
            return None, None, None

        # Determine file extension
        ext = mimetypes.guess_extension(content_type)
        if not ext:
            if content_type == "image/jpeg":
                ext = ".jpg"
            else:
                ext = ".dat"

        if content_type == "text/html":
            ext = ".htm"

        # Build filename following Go script logic: {savedir}/{mimetype}/{idx}{ext}
        filename = os.path.join(save_dir, content_type, f"{index}{ext}")

        # Get Content-ID and Content-Location headers
        content_id = part.get("Content-ID")
        content_location = part.get("Content-Location")

        return filename, content_id, content_location

    # Process all parts
    html_part_found = False
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue

        content_type = part.get_content_type()
        if not content_type:
            continue

        # Skip the first HTML part (this becomes the main HTML file)
        if content_type == "text/html" and not html_part_found:
            html_part_found = True
            continue

        filename, content_id, content_location = process_part(part, part_index)

        if filename:
            # Map Content-ID to filename (remove angle brackets if present)
            if content_id:
                clean_cid = content_id.strip("<>")
                content_id_to_file[f"cid:{clean_cid}"] = filename
                content_id_to_file[clean_cid] = filename  # Also without cid: prefix
                print(f"Mapped Content-ID '{clean_cid}' to '{filename}'")

            # Map Content-Location to filename
            if content_location:
                content_location_to_file[content_location] = filename
                print(f"Mapped Content-Location '{content_location}' to '{filename}'")

        part_index += 1

    return content_id_to_file, content_location_to_file


def replace_all_references_in_file(file_path, base_path, cid_mapping, location_mapping, backup=False):
    """
    Replace ALL occurrences of Content-IDs and Content-Locations in any file
    with their corresponding local file paths.

    Args:
        file_path: Path to the file to process
        cid_mapping: Dictionary mapping Content-IDs to local file paths
        location_mapping: Dictionary mapping Content-Locations to local file paths
        backup: Whether to create a backup of the original file

    Returns:
        tuple: (success: bool, replacements_made: int)
    """
    file_path = Path(file_path)
    base_path = Path(base_path)

    if not file_path.exists():
        print(f"File not found: {file_path}")
        return False, 0

    print(f"\nProcessing file for all reference replacements: {file_path}")

    # Create backup if requested
    if backup:
        backup_path = file_path.with_suffix(file_path.suffix + ".backup")
        if not backup_path.exists():
            import shutil

            shutil.copy2(file_path, backup_path)
            print(f"  Created backup: {backup_path}")

    # Read file content (try different encodings)
    content = None
    encoding_used = None

    for encoding in ["utf-8", "utf-8-sig"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            encoding_used = encoding
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        print("  ❌ Could not read file with any encoding")
        return False, 0

    print(f"  📄 File read successfully using {encoding_used} encoding")

    replacements_made = 0

    # Combine all mappings for easier processing
    all_mappings = {}
    all_mappings.update(cid_mapping)
    all_mappings.update(location_mapping)

    # Sort by length (longest first) to avoid partial replacements
    sorted_refs = sorted(all_mappings.keys(), key=len, reverse=True)

    print(f"  🔍 Checking {len(sorted_refs)} possible references...")

    for original_ref in sorted_refs:
        original_ref_filt = original_ref

        if original_ref.startswith("cid:"):
            original_ref_filt = original_ref[4:]
        elif "/" in original_ref:
            original_ref_split = str(Path(original_ref)).split("/")
            original_ref_filt = original_ref_split[-1]

        if original_ref_filt in content:
            local_file = all_mappings[original_ref]

            # Convert to relative path from the current file location
            full_path = base_path / local_file
            relative_path = os.path.relpath(full_path, file_path.parent)

            pattern = rf'["\']([^"\']*?)({re.escape(original_ref_filt)})["\']'

            # Check if the target file actually exists
            try:
                if full_path.exists():
                    # Count occurrences before replacement
                    occurrences = len(re.findall(pattern, content))  # content.count(original_ref)
                    sub = relative_path  # f'"{relative_path}"'
                    content = re.sub(pattern, sub, content)
                    # content = content.replace(original_ref, relative_path)
                    replacements_made += occurrences
                    print(f"    ✅ Replaced {occurrences}x '{original_ref}' → '{relative_path}'")
                else:
                    print(f"    ⚠️  Skipped '{original_ref}' (target file doesn't exist: {full_path})")
            except (OSError, ValueError) as e:
                print(f"    ⚠️  Skipped '{original_ref}' (path error: {e})")

    # Write back the updated content if changes were made
    if replacements_made > 0:
        try:
            with open(file_path, "w", encoding=encoding_used) as f:
                f.write(content)
            print(f"  ✅ Made {replacements_made} total replacements in {file_path}")
            return True, replacements_made
        except Exception as e:
            print(f"  ❌ Failed to write file: {e}")
            return False, 0
    else:
        print(f"  ℹ️  No references found to replace in {file_path}")
        return False, 0


def update_all_refs(html_file, mhtml_file):
    html_path = Path(html_file)

    if not mhtml_file or not Path(mhtml_file).exists():
        print("MHTML file not found. Please provide the original MHTML file.")
        return False

    print(f"Parsing MHTML file: {mhtml_file}")

    # Parse MHTML to get Content-ID mappings
    cid_mapping, location_mapping = parse_mhtml_content_mapping(mhtml_file)

    if not cid_mapping and not location_mapping:
        print("No Content-ID or Content-Location mappings found in MHTML file")
        return False

    base_path = html_path.parent
    text_assets_path = base_path / "page_files/text"

    if text_assets_path.exists():
        files = [str(file) for file in text_assets_path.rglob("*") if file.is_file()]

        for file in files:
            if not file.startswith("."):
                print(f"Replacing refs in {Path(file).name} ...")
                replace_all_references_in_file(file, base_path, cid_mapping, location_mapping)
    else:
        print("No page_files/text directory to update files in!")

    replace_all_references_in_file(html_path, base_path, cid_mapping, location_mapping)


# -----------------------------------------------------------------------------
# Public helpers
# -----------------------------------------------------------------------------


def normalize_selector(selector: dict[str, Any]) -> dict[str, Any]:
    """Normalize a selector by removing dynamic parts like session IDs and page visit IDs.

    Args:
        selector: The selector dictionary containing css_selector, xpath_selector etc.

    Returns:
        A normalized copy of the selector with dynamic parts stripped out
    """
    normalized = selector.copy()

    # Helper to normalize URL parameters
    def normalize_url_params(url: str) -> str:
        # Keep static params, remove dynamic ones like duid, pv
        parsed = urlparse(url)
        if not parsed.query:
            return url

        params = parse_qs(parsed.query)
        # Remove known dynamic parameters
        dynamic_params = ["duid", "pv", "cb", "name", "version", "appId"]  # Added cb and name which are dynamic
        for param in dynamic_params:
            params.pop(param, None)

        # Rebuild URL with remaining params
        normalized_query = urlencode(params, doseq=True) if params else ""
        parts = list(parsed)
        parts[4] = normalized_query  # 4 is query index
        return "".join(part for part in parts if part)

    # Helper to normalize URLs in CSS selectors
    def normalize_urls_in_selector(css: str) -> str:
        # Find all URLs in src/href attributes
        url_pattern = r'\[(src|href)="([^"]+)"\]'

        def replace_url(match: re.Match[str]) -> str:
            attr, url = match.groups()
            normalized_url = normalize_url_params(url)
            return f'[{attr}="{normalized_url}"]'

        return re.sub(url_pattern, replace_url, css)

    # Normalize CSS selector
    if "css_selector" in normalized:
        css = normalized["css_selector"]
        # Replace dynamic attributes in CSS selectors
        css = re.sub(r'\[id="[^"]*"\]', "[id]", css)
        # Handle data-* attributes which are often dynamic
        css = re.sub(r'\[data-[^=]+=["\'"][^\'"]*["\']\]', "", css)
        # Handle dynamic nth-of-type
        css = re.sub(r":nth-of-type\(\d+\)", "", css)
        # Handle dynamic name attributes
        css = re.sub(r'\[name="[^"]*"\]', "[name]", css)
        # Normalize URLs in src/href attributes
        css = normalize_urls_in_selector(css)
        normalized["css_selector"] = css

    # Normalize xpath selector
    if "xpath_selector" in normalized:
        xpath = normalized["xpath_selector"]
        # Remove position predicates which can be dynamic
        xpath = re.sub(r"\[\d+\]", "", xpath)
        normalized["xpath_selector"] = xpath

    # Normalize iframe parent selectors
    if "iframe_parent_css_selectors" in normalized:
        normalized["iframe_parent_css_selectors"] = [
            normalize_urls_in_selector(selector) for selector in normalized["iframe_parent_css_selectors"]
        ]

    return normalized


def compare_selector_href_agnostic(sel1: str, sel2: str) -> bool:
    pattern = r'\[(href|src)="[^"]*"\]'

    sel1_re = re.sub(pattern, "", sel1)
    sel2_re = re.sub(pattern, "", sel2)

    return sel1_re == sel2_re


def filter_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ret: list[dict[str, Any]] = []
    bad_selections = ["html/body", "html/body/div[1]"]

    for action in actions:
        if action["selector"]["xpath_selector"] not in bad_selections:
            ret.append(action)

    return ret


def filter_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ret: list[dict[str, Any]] = []
    bad_selections = ["xpath=html/body", "xpath=html/body/div[1]"]

    for node in nodes:
        if node["selectors"][1] not in bad_selections:
            ret.append(node)

    return ret


def compare_actions(
    static_actions: list[dict[str, Any]], live_actions: list[dict[str, Any]], lax: bool = False
) -> None:
    """Compare two lists of actions for equality.

    Args:
        static_actions: List of actions from the static snapshot
        live_actions: List of actions from the live snapshot

    Raises:
        AssertionError: If the actions don't match
    """
    if lax:
        static_actions = filter_actions(static_actions)
        live_actions = filter_actions(live_actions)

    if len(live_actions) != len(static_actions):
        logger.error("Actions length mismatch:")
        logger.error(f"Static actions ({len(static_actions)} items):")
        for item in static_actions:
            logger.error(f"  {item.get('type', '?')} - {item.get('text_label', '?')}")
        logger.error(f"Live actions ({len(live_actions)} items):")
        for item in live_actions:
            logger.error(f"  {item.get('type', '?')} - {item.get('text_label', '?')}")
        raise AssertionError(f"Actions length mismatch: live={len(live_actions)} != static={len(static_actions)}")

    for i, (static_item, live_item) in enumerate(zip(static_actions, live_actions)):
        # Compare type and category
        for key in ["type", "category"]:
            if static_item[key] != live_item[key]:
                logger.error(f"Action mismatch for key '{key}' at index {i}:")
                logger.error(f"Static: {static_item[key]}")
                logger.error(f"Live  : {live_item[key]}")
                raise AssertionError(f"Action mismatch for key '{key}'")

        _static_item_selector = static_item["selector"]
        _live_item_selector = live_item["selector"]
        # normalize selectors
        static_item_selector = normalize_selector(_static_item_selector)
        live_item_selector = normalize_selector(_live_item_selector)
        # Compare normalized selectors
        for selector_key in ["in_iframe", "in_shadow_root"]:
            if static_item_selector.get(selector_key) != live_item_selector.get(selector_key):
                logger.error(f"Action selector mismatch for key '{selector_key}' at index {i}:")
                logger.error(f"Static: {static_item.get(selector_key)}")
                logger.error(f"Live  : {live_item.get(selector_key)}")
                raise AssertionError(f"Action selector mismatch for key '{selector_key}'")
        # playwright_selector, xpath_selector, css_selector
        for selector_key in ["xpath_selector", "css_selector"]:
            selector_mismatch = static_item_selector[selector_key] != live_item_selector[selector_key]

            if lax:
                selector_mismatch = not compare_selector_href_agnostic(
                    static_item_selector[selector_key], live_item_selector[selector_key]
                )

            if selector_mismatch:
                logger.error(f"Action selector mismatch for key '{selector_key}' at index {i}:")
                logger.error(f"Static (normalized): {static_item_selector[selector_key]}")
                logger.error(f"Live   (normalized): {live_item_selector[selector_key]}")
                logger.error("--------------------------------")
                logger.error(f"Static             : {static_item_selector[selector_key]}")
                logger.error(f"Live               : {live_item_selector[selector_key]}")
                raise AssertionError(f"Action selector mismatch for key '{selector_key}'")
        # last is :  "iframe_parent_css_selectors"
        # if static_item_selector['iframe_parent_css_selectors'] != live_item_selector['iframe_parent_css_selectors']:
        #     logger.error(f"Action selector mismatch for key 'iframe_parent_css_selectors' at index {i}:")
        #     logger.error(f"Static: {static_item_selector['iframe_parent_css_selectors']}")
        #     logger.error(f"Live  : {live_item_selector['iframe_parent_css_selectors']}")
        #     raise AssertionError(f"Action selector mismatch for key 'iframe_parent_css_selectors'")


def compare_nodes(static_nodes: list[dict[str, Any]], live_nodes: list[dict[str, Any]], lax: bool = False) -> None:
    """Compare two lists of nodes for equality.

    Args:
        static_nodes: List of nodes from the static snapshot
        live_nodes: List of nodes from the live snapshot

    Raises:
        AssertionError: If the nodes don't match
    """
    if lax:
        static_nodes = filter_nodes(static_nodes)
        live_nodes = filter_nodes(live_nodes)

    if len(live_nodes) != len(static_nodes):
        logger.error("Nodes length mismatch:")
        logger.error(f"Static nodes ({len(static_nodes)} items):")
        for item in static_nodes:
            logger.error(f"  {item.get('role', '?')} - {item.get('text', '?')}")
        logger.error(f"Live nodes ({len(live_nodes)} items):")
        for item in live_nodes:
            logger.error(f"  {item.get('role', '?')} - {item.get('text', '?')}")
        raise AssertionError(f"Nodes length mismatch: {len(live_nodes)} != {len(static_nodes)}")

    for i, (static_item, live_item) in enumerate(zip(static_nodes, live_nodes)):
        # Compare all node attributes except selectors
        if static_item["role"] != live_item["role"]:
            logger.error(f"Node mismatch for key 'role' at index {i}:")
            logger.error(f"Static: {static_item['role']}")
            logger.error(f"Live  : {live_item['role']}")
            raise AssertionError("Node mismatch for key 'role'")
        # check bbox separately. Make sure to
        for key in ["x", "y", "width", "height", "viewport_width", "viewport_height"]:
            if int(static_item["bbox"][key]) != int(live_item["bbox"][key]):
                logger.error(f"Node mismatch for key '{key}' at index {i}:")
                logger.error(f"Static: {static_item['bbox'][key]}")
                logger.error(f"Live  : {live_item['bbox'][key]}")
                if not lax:
                    raise AssertionError(f"Node mismatch for key '{key}'")

        # check:  'attributes', 'computed_attributes',
        static_attributes = static_item["attributes"]
        live_attributes = live_item["attributes"]

        all_attrs_keys = set(static_attributes.keys()) | set(live_attributes.keys())
        for key in all_attrs_keys:
            if key in ["src", "href"]:
                continue

            if static_attributes.get(key) != live_attributes.get(key):
                logger.error(f"Node mismatch for key '{key}' at index {i}:")
                logger.error(f"Static: {static_attributes[key]}")
                logger.error(f"Live  : {live_attributes[key]}")

        # Compare selectors if they exist
        if "selectors" in static_item and "selectors" in live_item:
            static_selectors = static_item["selectors"]
            live_selectors = live_item["selectors"]

            if len(static_selectors) != len(live_selectors):
                logger.error(f"Node selectors length mismatch at index {i}:")
                logger.error(f"Static selectors: {static_selectors}")
                logger.error(f"Live selectors  : {live_selectors}")
                raise AssertionError("Node selectors length mismatch")

            # Compare each selector after normalization
            for static_sel, live_sel in zip(static_selectors, live_selectors):
                # Extract selector type (css= or xpath=) and the actual selector
                static_type, static_value = static_sel.split("=", 1) if "=" in static_sel else ("", static_sel)
                live_type, live_value = live_sel.split("=", 1) if "=" in live_sel else ("", live_sel)

                if static_type != live_type:
                    logger.error(f"Node selector type mismatch at index {i}:")
                    logger.error(f"Static: {static_type}")
                    logger.error(f"Live  : {live_type}")
                    raise AssertionError("Node selector type mismatch")

                # Normalize and compare the actual selector values
                normalized_static = (
                    normalize_selector({"css_selector": static_value})["css_selector"]
                    if static_type == "css"
                    else static_value
                )
                normalized_live = (
                    normalize_selector({"css_selector": live_value})["css_selector"]
                    if live_type == "css"
                    else live_value
                )

                selector_mismatch = normalized_static != normalized_live

                if lax:
                    selector_mismatch = not compare_selector_href_agnostic(normalized_static, normalized_live)

                if selector_mismatch:
                    logger.error(f"Node selector value mismatch at index {i}:")
                    logger.error(f"Static: {static_sel}")
                    logger.error(f"Live  : {live_sel}")
                    logger.error(f"Normalized static: {normalized_static}")
                    logger.error(f"Normalized live  : {normalized_live}")
                    raise AssertionError("Node selector value mismatch")


def urls() -> list[str]:
    return [
        "https://www.allrecipes.com/gochujang-scrambled-eggs-recipe-11772055",
        "https://x.com",
        "https://www.ubereats.com",
        "https://www.wise.com",
        "https://www.quince.com/women/organic-cotton-high-rise-relaxed-straight-jeans--28-inseam?color=atlantic-blue&tracker=landingPage__flat_product_list",
        # "https://www.google.com",
        "https://www.google.com/flights",
        "https://www.google.com/maps",
        "https://news.google.com",
        "https://translate.google.com",
        "https://www.linkedin.com",
        "https://www.instagram.com",
        "https://notte.cc",
        "https://www.bbc.com/news/articles/c3en0qwp44do",
        "https://www.amazon.com/PlayStation%C2%AE5-Digital-slim-PlayStation-5/dp/B0CL5KNB9M/ref=sr_1_1?crid=3EXOUDOE350CS&dib=eyJ2IjoiMSJ9.Hf4Fkrl_e0M9CGAlK8cZ5MuOAgb7OnfXc3OZbD53izFiM4CX9evFfgnKi7f1F8FoAnkbC3VpGlvJEAiXwwSVhL_AI8C5uNbVpEDwL3yCMmPF6a86CHCKPPds1W8_cTkE0uIn_jT-AEtw5HnRa3ucVVDQckhWxlacHr2xa-bOViSBcjjS9juEqEuKHyItOm4tUjqGQIPN6vrO6ndh-YXSv7bb7CwuTtZd0sAk9rYQTKA.DJlSxXq1tL9EDAXvLHUGM0Z20FP2BCTK2stKhJI2nyo&dib_tag=se&keywords=ps5&qid=1753141606&sprefix=ps5%2Caps%2C176&sr=8-1",
        "https://www.apple.com/apple-music/",
        "https://arxiv.org/abs/1706.03762",
        "https://www.coursera.org/learn/scala-functional-programming?specialization=scala",
        "https://dictionary.cambridge.org",
        # "https://www.espn.com",
        "https://www.booking.com/hotel/us/springhill-suites-by-marriott-new-york-manhattan-times-square-36th-st.en-gb.html?aid=2311236&label=en-us-booking-desktop-hdfqyDAE2wG%2AEqnCmUZVBgS652734911659%3Apl%3Ata%3Ap1%3Ap2%3Aac%3Aap%3Aneg%3Afi%3Atikwd-334108349%3Alp9061268%3Ali%3Adec%3Adm&sid=dc510b3c91b1f3973b78291ab05505f3&dist=0&group_adults=2&group_children=0&hapos=1&hpos=1&nflt=class%3D4&no_rooms=1&req_adults=2&req_children=0&room1=A%2CA&sb_price_type=total&sr_order=popularity&srepoch=1753141708&srpvid=b2c1a69f7bea22f024d733dbc8158b2e&type=total&ucfs=1&",
    ]


class SnapshotMetadata(BaseModel):
    url: str
    created_at: str = Field(default_factory=lambda: dt.datetime.now().isoformat())
    version: str = __version__


class ActionResolutionReport(BaseModel):
    action_id: str
    locator: str | None
    error: str | None
    success: bool


# -----------------------------------------------------------------------------
# Default viewport size (shared across snapshots & tests)
# -----------------------------------------------------------------------------

VIEWPORT_WIDTH: Final[int] = 1280
VIEWPORT_HEIGHT: Final[int] = 1080


def dump_interaction_nodes(session: notte.Session) -> list[dict[str, object]]:
    """Return the serialised interaction nodes for the current session."""
    nodes_dump: list[dict[str, object]] = []
    for node in session.snapshot.interaction_nodes():
        selectors: list[str] = []
        if node.computed_attributes.selectors is not None:
            selectors = node.computed_attributes.selectors.selectors()

        nodes_dump.append(
            {
                "id": node.id,
                "role": node.get_role_str(),
                "text": node.text,
                "inner_text": node.inner_text(),
                "selectors": selectors,
                "attributes": {k: v for k, v in asdict(node.attributes).items() if v is not None}
                if node.attributes is not None
                else None,
                "computed_attributes": {
                    k: v for k, v in asdict(node.computed_attributes).items() if v is not None and k != "selectors"
                },
                "bbox": node.bbox.model_dump(exclude_none=True) if node.bbox is not None else None,
                "subtree_ids": node.subtree_ids,
            }
        )

    # Sort nodes by xpath selector
    def get_xpath_selector(node_dict: dict[str, Any]) -> str:
        selectors = node_dict.get("selectors", [])
        for selector in selectors:
            if selector.startswith("xpath="):
                return selector[6:]  # Remove "xpath=" prefix
        return ""  # Fallback for nodes without xpath

    nodes_dump.sort(key=get_xpath_selector)

    return nodes_dump


def extract_selector(locator_str: str) -> str | None:
    match = re.search(r"selector='([^']+)'", locator_str)
    return match.group(1) if match else None


async def dump_action_resolution_reports(
    session: notte.Session, actions: Sequence[InteractionAction]
) -> list[ActionResolutionReport]:
    action_resolution_reports: list[ActionResolutionReport] = []
    for action in actions:
        try:
            locator = await session.locate(action)
            if locator is None:
                action_resolution_reports.append(
                    ActionResolutionReport(action_id=action.id, locator=None, error="Locator is None", success=False)
                )
            else:
                text_selector = extract_selector(str(locator))
                count = await locator.count()
                if count == 0:
                    action_resolution_reports.append(
                        ActionResolutionReport(
                            action_id=action.id,
                            locator=text_selector,
                            error="Locator does not correspond to any element",
                            success=False,
                        )
                    )
                elif count > 1:
                    action_resolution_reports.append(
                        ActionResolutionReport(
                            action_id=action.id,
                            locator=text_selector,
                            error="Locator corresponds to multiple elements",
                            success=False,
                        )
                    )
                else:
                    action_resolution_reports.append(
                        ActionResolutionReport(
                            action_id=action.id,
                            locator=text_selector,
                            error=None,
                            success=True,
                        )
                    )
        except ValueError as e:
            # Handle the case when element is not in an iframe
            if "Node is not in an iframe" in str(e):
                action_resolution_reports.append(
                    ActionResolutionReport(
                        action_id=action.id,
                        locator=None,
                        error=str(e),
                        success=False,
                    )
                )
            else:
                raise
    return action_resolution_reports


async def get_mhtml_snapshot(save_dir: Path, session: notte.Session) -> None:
    client = await session.window.get_cdp_session()
    res = await client.send("Page.captureSnapshot")
    mhtml = res["data"]
    mhtml_path = save_dir / "page.mhtml"

    with open(mhtml_path, mode="w", encoding="UTF-8", newline="\n") as file:
        _ = file.write(mhtml)

    html_path = str(save_dir / "page.html")

    convert_mhtml(str(mhtml_path), output_file=html_path, verbose=True)
    comprehensive_relative_path_fix(html_path)
    remove_base_tags(html_path)
    update_all_refs(html_path, str(mhtml_path))


def save_snapshot(
    save_dir: Path, session: notte.Session, url: str | None = None, wait_time: int = 10, save_html: bool = False
) -> None:
    """
    Save a snapshot of the current session to the given directory.

    Args:
        save_dir: The directory to save the snapshot to.
        session: The session to save.
        url: The URL of the page to save.
        save_html: whether to save html
    Saves files:
        metadata.json: Metadata about the snapshot.
        actions.json: The interaction actions of the page.
        page_old.html: The HTML content of the page.
        page.html: Renderable HTML page.
        page_files/: Page assets.
        nodes.json: The interaction nodes of the page.
        screenshot.png: The screenshot of the page.
        locator_reports.json: The locator reports of the page.
    """
    _ = session.execute(type="goto", value=url)

    obs = session.observe(perception_type="fast")

    if wait_time > 0:
        # manualy wait 5 seconds
        time.sleep(wait_time)

        # retry observe
        obs = session.observe(perception_type="fast")

    # save metadata
    with open(save_dir / "metadata.json", "w") as fp:
        json.dump(SnapshotMetadata(url=obs.metadata.url).model_dump(), fp, indent=2, ensure_ascii=False)

    # save sorted actions
    with open(save_dir / "actions.json", "w") as fp:
        actions = obs.space.interaction_actions
        # Convert actions to dict and add selector and text_label
        action_dicts: list[dict[str, Any]] = []
        for action in actions:
            action_dict = action.model_dump()
            action_dict["selector"] = {
                "css_selector": action.selector.css_selector,
                "xpath_selector": action.selector.xpath_selector,
                "in_iframe": action.selector.in_iframe,
                "in_shadow_root": action.selector.in_shadow_root,
                "iframe_parent_css_selectors": action.selector.iframe_parent_css_selectors,
                "playwright_selector": action.selector.playwright_selector,
            }
            action_dict["text_label"] = action.text_label
            action_dicts.append(action_dict)

        actions = sorted(action_dicts, key=lambda x: x["selector"]["xpath_selector"])
        json.dump([action for action in actions], fp, indent=2, ensure_ascii=False)

    if save_html:
        with open(save_dir / "page_old.html", "w") as fp:
            _ = fp.write(session.snapshot.html_content)

        # Snapshot using mhtml/getting all assets
        asyncio.run(get_mhtml_snapshot(save_dir, session))

    # save node dump
    nodes_dump = dump_interaction_nodes(session)
    with open(save_dir / "nodes.json", "w") as fp:
        json.dump(nodes_dump, fp, indent=2, ensure_ascii=False)

    # save screenshot with bourding boxes
    image = obs.screenshot.display(type="full")
    if image is None:
        raise AssertionError(f"Screenshot is None for {save_dir}")
    image.save(save_dir / "screenshot.png")

    # check locate interaction nodes
    # with open(save_dir / "locator_reports.json", "w") as fp:
    #     reports: list[ActionResolutionReport] = asyncio.run(
    #         dump_action_resolution_reports(session, obs.space.interaction_actions)
    #     )
    #     json.dump([report.model_dump() for report in reports], fp, indent=2, ensure_ascii=False)

    # make empty file for missing action annotation
    # with open(save_dir / "missing_actions.json", "w") as fp:
    #     json.dump([], fp, indent=2, ensure_ascii=False)


def get_snapshot_dir(
    url: str,
    sub_dir: str | None = None,
    type: Literal["static", "live", "local", "existing_static", "replay"] = "static",
) -> Path:
    parsed: ParseResult = urlparse(url)
    name: Final[str] = Path(parsed.netloc.replace("www.", "")) / (parsed.path.strip("/") or "index")  # type: ignore
    match type:
        case "static":
            save_dir = SNAPSHOT_DIR_STATIC / name
        case "live":
            save_dir = SNAPSHOT_DIR_LIVE / name
        case "local":
            save_dir = SNAPSHOT_DIR_LOCAL / name
        case "replay":
            save_dir = SNAPSHOT_DIR_REPLAY / name
        case "existing_static":
            save_dir = get_last_static_snapshot_dir() / name
        case _:
            raise ValueError(f"Invalid type: {type}")
    if sub_dir is not None:
        save_dir = save_dir / sub_dir
    _ = save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir


def save_snapshot_static(
    url: str,
    sub_dir: str | None = None,
    type: Literal["static", "live", "replay"] = "static",
    wait_time: int = 10,
    save_from_local: bool = True,
) -> Path:
    save_dir = get_snapshot_dir(url=url, sub_dir=sub_dir, type=type)
    _ = save_dir.mkdir(parents=True, exist_ok=True)
    save_html = False
    headless = True
    # Create a fresh Notte session for each page to avoid side-effects.

    if type == "static":
        save_html = True

        if save_from_local:
            with notte.Session(
                headless=False,
                viewport_width=VIEWPORT_WIDTH,
                viewport_height=VIEWPORT_HEIGHT,
            ) as session:
                save_snapshot(save_dir=save_dir, session=session, url=url, wait_time=wait_time, save_html=save_html)

            save_html = False

            static_dir = get_snapshot_dir(url, type="existing_static")
            port = get_free_port()
            server = LocalServer(port=port, directory=static_dir)
            server.start()

            url = f"http://localhost:{port}/page.html"

    if type == "replay":
        # update url to take preivous "static" snapshot url file
        static_dir = get_snapshot_dir(url, type="existing_static")
        url = f"file://{quote(str(static_dir / 'page.html'))}"  # url encode

    # if using locally saved mhtml, serve page with local server
    if type == "local":
        static_dir = get_snapshot_dir(url, type="existing_static")
        port = get_free_port()
        server = LocalServer(port=port, directory=static_dir)
        server.start()

        url = f"http://localhost:{port}/page.html"

    with notte.Session(
        headless=headless,
        viewport_width=VIEWPORT_WIDTH,
        viewport_height=VIEWPORT_HEIGHT,
    ) as session:
        save_snapshot(save_dir=save_dir, session=session, url=url, wait_time=wait_time, save_html=save_html)

    if type == "local" or (type == "static" and save_from_local):
        server.stop()

    return save_dir


def save_single_snapshot_trajectory(url: str, task: str) -> None:
    _ = SNAPSHOT_DIR_TRAJECTORY.mkdir(parents=True, exist_ok=True)

    # Create a fresh Notte session for each page to avoid side-effects.
    with notte.Session(
        headless=True,
        viewport_width=VIEWPORT_WIDTH,
        viewport_height=VIEWPORT_HEIGHT,
    ) as session:
        _ = session.execute(type="goto", value=url)
        obs = session.observe(perception_type="fast")

        obs_list: list[Observation] = [obs]

        agent = notte.Agent(session=session, reasoning_model="vertex_ai/gemini-2.0-flash")
        response = agent.run(task=task, url=url)

        # If response contains trajectory with multiple observations, add them to the list
        for step in response.trajectory:
            match step:
                case Observation():
                    obs_list.append(step)
                case _:
                    # skip
                    pass

        for i, obs in enumerate(obs_list):
            save_dir = get_snapshot_dir(url, sub_dir=f"trajectory/step_{i}")
            save_snapshot(save_dir, session, obs.metadata.url)


def save_snapshot_trajectory(urls: list[str], tasks: list[str]) -> None:
    for url, task in zip(urls, tasks):
        save_single_snapshot_trajectory(url, task)


@pytest.mark.skip(reason="Run this test to generate new snapshots")
@pytest.mark.parametrize("url", urls())
def test_generate_observe_snapshot(url: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""
    # TODO move ts
    _ = save_snapshot_static(url, type="static", wait_time=8, save_from_local=True)


@pytest.mark.skip(reason="Run this test to compare live load with saved snapshots")
@pytest.mark.parametrize("url", urls(), ids=lambda x: x.split("?")[0].split("https://")[-1])
def test_compare_live_observe_snapshot(url: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""
    static_dir = get_snapshot_dir(url, type="existing_static")
    static_actions = json.loads((static_dir / "actions.json").read_text(encoding="utf-8"))
    live_dir = save_snapshot_static(url, type="live")

    # Compare actions.json
    live_actions = json.loads((live_dir / "actions.json").read_text(encoding="utf-8"))
    for _ in range(3):
        live_dir = save_snapshot_static(url, type="live")
        live_actions = json.loads((live_dir / "actions.json").read_text(encoding="utf-8"))
        # if len live_actions < len static_actions, then let's retry to avoid missing actions due to network delay
        if len(live_actions) >= len(static_actions):
            break
    compare_actions(static_actions, live_actions)

    # Compare nodes.json
    static_nodes = json.loads((static_dir / "nodes.json").read_text(encoding="utf-8"))
    live_nodes = json.loads((live_dir / "nodes.json").read_text(encoding="utf-8"))
    compare_nodes(static_nodes, live_nodes)


@pytest.mark.skip(reason="Run this test to compare with basic saved snapshots")
@pytest.mark.parametrize("url", urls(), ids=lambda x: x.split("?")[0].split("https://")[-1])
def test_compare_static_observe_snapshot(url: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""
    static_dir = get_snapshot_dir(url, type="existing_static")
    static_actions = json.loads((static_dir / "actions.json").read_text(encoding="utf-8"))
    live_dir = save_snapshot_static(url, type="replay")

    # Compare actions.json
    live_actions = json.loads((live_dir / "actions.json").read_text(encoding="utf-8"))
    for _ in range(3):
        live_dir = save_snapshot_static(url, type="replay")
        live_actions = json.loads((live_dir / "actions.json").read_text(encoding="utf-8"))
        # if len live_actions < len static_actions, then let's retry to avoid missing actions due to network delay
        if len(live_actions) >= len(static_actions):
            break
    compare_actions(static_actions, live_actions)

    # Compare nodes.json
    static_nodes = json.loads((static_dir / "nodes.json").read_text(encoding="utf-8"))
    live_nodes = json.loads((live_dir / "nodes.json").read_text(encoding="utf-8"))
    compare_nodes(static_nodes, live_nodes)


# @pytest.mark.skip(reason="Run this test to compare with mhtml saved snapshots")
@pytest.mark.parametrize("url", urls(), ids=lambda x: x.split("?")[0].split("https://")[-1])
def test_compare_local_observe_snapshot(url: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""
    static_dir = get_snapshot_dir(url, type="existing_static")
    static_actions = json.loads((static_dir / "actions.json").read_text(encoding="utf-8"))
    live_dir = save_snapshot_static(url, type="replay", wait_time=0)

    # Compare actions.json
    live_actions = json.loads((live_dir / "actions.json").read_text(encoding="utf-8"))
    for _ in range(3):
        # if len live_actions < len static_actions, then let's retry to avoid missing actions due to network delay
        if len(live_actions) >= len(static_actions):
            break
        live_dir = save_snapshot_static(url, type="replay", wait_time=5)
        live_actions = json.loads((live_dir / "actions.json").read_text(encoding="utf-8"))
    compare_actions(static_actions, live_actions, lax=True)

    # Compare nodes.json
    static_nodes = json.loads((static_dir / "nodes.json").read_text(encoding="utf-8"))
    live_nodes = json.loads((live_dir / "nodes.json").read_text(encoding="utf-8"))
    compare_nodes(static_nodes, live_nodes, lax=True)
