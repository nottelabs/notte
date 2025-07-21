import asyncio
import datetime as dt
import json
import re
import time
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final, Literal
from urllib.parse import ParseResult, parse_qs, urlencode, urlparse

import pytest
from loguru import logger
from notte_core import __version__
from notte_core.actions import InteractionAction
from notte_core.browser.observation import Observation
from pydantic import BaseModel, Field

import notte

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
DOM_REPORTS_DIR: Final[Path] = Path(__file__).parent.parent.parent / ".dom_reports"
SNAPSHOT_DIR_STATIC: Final[Path] = DOM_REPORTS_DIR / Path("static_" + dt.datetime.now().strftime("%Y-%m-%d"))
SNAPSHOT_DIR_LIVE: Final[Path] = DOM_REPORTS_DIR / Path("live_" + dt.datetime.now().strftime("%Y-%m-%d"))
SNAPSHOT_DIR_TRAJECTORY: Final[Path] = DOM_REPORTS_DIR / Path("trajectory_" + dt.datetime.now().strftime("%Y-%m-%d"))

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


def compare_actions(static_actions: list[dict[str, Any]], live_actions: list[dict[str, Any]]) -> None:
    """Compare two lists of actions for equality.

    Args:
        static_actions: List of actions from the static snapshot
        live_actions: List of actions from the live snapshot

    Raises:
        AssertionError: If the actions don't match
    """
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
            if static_item_selector[selector_key] != live_item_selector[selector_key]:
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


def compare_nodes(static_nodes: list[dict[str, Any]], live_nodes: list[dict[str, Any]]) -> None:
    """Compare two lists of nodes for equality.

    Args:
        static_nodes: List of nodes from the static snapshot
        live_nodes: List of nodes from the live snapshot

    Raises:
        AssertionError: If the nodes don't match
    """
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

                if normalized_static != normalized_live:
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
        # "https://www.google.com/flights",
        # "https://www.google.com/maps",
        # "https://news.google.com",
        # "https://translate.google.com",
        # "https://www.linkedin.com",
        # "https://www.instagram.com",
        # "https://notte.cc",
        # "https://www.bbc.com",
        # "https://www.allrecipes.com",
        # "https://www.amazon.com",
        # "https://www.apple.com",
        # "https://arxiv.org",
        # "https://www.coursera.org",
        # "https://dictionary.cambridge.org",
        # "https://www.espn.com",
        # "https://booking.com",
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


def save_snapshot(save_dir: Path, session: notte.Session, url: str | None = None, wait_time: int = 10) -> None:
    """
    Save a snapshot of the current session to the given directory.

    Args:
        save_dir: The directory to save the snapshot to.
        session: The session to save.
        url: The URL of the page to save.
    Saves files:
        metadata.json: Metadata about the snapshot.
        actions.json: The interaction actions of the page.
        page.html: The HTML content of the page.
        nodes.json: The interaction nodes of the page.
        screenshot.png: The screenshot of the page.
        locator_reports.json: The locator reports of the page.
    """

    obs = session.observe(url=url)
    # manualy wait 5 seconds
    time.sleep(wait_time)
    # retry observe
    obs = session.observe()

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

    with open(save_dir / "page.html", "w") as fp:
        _ = fp.write(session.snapshot.html_content)

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
    with open(save_dir / "locator_reports.json", "w") as fp:
        reports: list[ActionResolutionReport] = asyncio.run(
            dump_action_resolution_reports(session, obs.space.interaction_actions)
        )
        json.dump([report.model_dump() for report in reports], fp, indent=2, ensure_ascii=False)

    # make empty file for missing action annotation
    with open(save_dir / "missing_actions.json", "w") as fp:
        json.dump([], fp, indent=2, ensure_ascii=False)


def get_snapshot_dir(url: str, sub_dir: str | None = None, type: Literal["static", "live"] = "static") -> Path:
    parsed: ParseResult = urlparse(url)
    name: Final[str] = Path(parsed.netloc.replace("www.", "")) / (parsed.path.strip("/") or "index")  # type: ignore
    save_dir = (SNAPSHOT_DIR_STATIC if type == "static" else SNAPSHOT_DIR_LIVE) / name
    if sub_dir is not None:
        save_dir = save_dir / sub_dir
    _ = save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir


def save_snapshot_static(
    url: str, sub_dir: str | None = None, type: Literal["static", "live"] = "static", wait_time: int = 10
) -> Path:
    save_dir = get_snapshot_dir(url, sub_dir, type)
    # Create a fresh Notte session for each page to avoid side-effects.
    with notte.Session(
        headless=True,
        enable_perception=False,
        viewport_width=VIEWPORT_WIDTH,
        viewport_height=VIEWPORT_HEIGHT,
    ) as session:
        save_snapshot(save_dir=save_dir, session=session, url=url, wait_time=wait_time)
    return save_dir


def save_snapshot_trajectory(url: str, task: str) -> None:
    _ = SNAPSHOT_DIR_TRAJECTORY.mkdir(parents=True, exist_ok=True)

    # Create a fresh Notte session for each page to avoid side-effects.
    with notte.Session(
        headless=True,
        enable_perception=False,
        viewport_width=VIEWPORT_WIDTH,
        viewport_height=VIEWPORT_HEIGHT,
    ) as session:
        obs = session.observe(url=url)

        obs_list: list[Observation] = [obs]

        agent = notte.Agent(session=session, reasoning_model="vertex_ai/gemini-2.0-flash")
        response = agent.run(task=task, url=url)

        # If response contains trajectory with multiple observations, add them to the list
        for step in response.trajectory:
            obs_list.append(step.obs)

        for i, obs in enumerate(obs_list):
            save_dir = get_snapshot_dir(url, sub_dir=f"trajectory/step_{i}")
            save_snapshot(save_dir, session, obs.metadata.url)


# @pytest.mark.skip(reason="Run this test to generate new snapshots")
@pytest.mark.parametrize("url", urls())
def test_generate_observe_snapshot(url: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""
    # TODO move ts
    _ = save_snapshot_static(url, type="static", wait_time=30)


@pytest.mark.parametrize("url", urls())
def test_compare_observe_snapshot(url: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""
    static_dir = get_snapshot_dir(url, type="static")
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

    # compare static and live

    # actual = dump_interaction_nodes(session)
    # expected = json.loads(json_path.read_text(encoding="utf-8"))
    # if actual != expected:
    #    raise AssertionError(f"Data snapshot mismatch for {name}")
