import asyncio
import datetime as dt
import json
import re
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlparse

from notte_core.utils import url
import pytest
from notte_core import __version__
from notte_core.actions import InteractionAction
from notte_core.browser.observation import Observation
from pydantic import BaseModel, Field

import notte

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
DOM_REPORTS_DIR: Final[Path] = Path(__file__).parent.parent.parent / ".dom_reports"
SNAPSHOT_DIR_STATIC: Final[Path] = DOM_REPORTS_DIR / Path('static_' + dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
SNAPSHOT_DIR_TRAJECTORY: Final[Path] = DOM_REPORTS_DIR / Path('trajectory_' + dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))

# -----------------------------------------------------------------------------
# Public helpers
# -----------------------------------------------------------------------------


def urls() -> list[str]:
    return [
        "https://allrecipes.com",
        "https://x.com",
        "https://www.ubereats.com",
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
            action_resolution_reports.append(
                ActionResolutionReport(
                    action_id=action.id,
                    locator=extract_selector(str(locator)) if locator is not None else None,
                    error=None,
                    success=locator is not None,
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


def save_snapshot(save_dir: Path, session: notte.Session, url: str) -> None:
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

    # save metadata
    with open(save_dir / "metadata.json", "w") as fp:
        json.dump(SnapshotMetadata(url=url).model_dump(), fp, indent=2, ensure_ascii=False)

    # save sorted actions
    with open(save_dir / "actions.json", "w") as fp:
        actions = obs.space.interaction_actions
        # Convert actions to dict and add selector and text_label
        action_dicts: list[dict[str, Any]] = []
        for action in actions:
            action_dict = action.model_dump()
            action_dict['selector'] = {
                'css_selector': action.selector.css_selector,
                'xpath_selector': action.selector.xpath_selector,
                'notte_selector': action.selector.notte_selector,
                'in_iframe': action.selector.in_iframe,
                'in_shadow_root': action.selector.in_shadow_root,
                'iframe_parent_css_selectors': action.selector.iframe_parent_css_selectors,
                'playwright_selector': action.selector.playwright_selector
            }
            action_dict['text_label'] = action.text_label
            action_dicts.append(action_dict)
                
        actions = sorted(action_dicts, key=lambda x: x['selector']['xpath_selector'])
        json.dump(
            [action for action in actions], fp, indent=2, ensure_ascii=False
        )

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


def save_snapshot_static(url: str) -> None:
    _ = SNAPSHOT_DIR_STATIC.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(url)

    name: Final[str] = Path(parsed.netloc.replace("www.", "")) / (parsed.path.strip("/") or "index") # type: ignore
    save_dir = SNAPSHOT_DIR_STATIC / name
    _ = save_dir.mkdir(parents=True, exist_ok=True)

    # Create a fresh Notte session for each page to avoid side-effects.
    with notte.Session(
        headless=True,
        enable_perception=False,
        viewport_width=VIEWPORT_WIDTH,
        viewport_height=VIEWPORT_HEIGHT,
    ) as session:

        save_snapshot(save_dir=save_dir, session=session, url=url)


def save_snapshot_trajectory(url: str, task: str) -> None:
    _ = SNAPSHOT_DIR_TRAJECTORY.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(url)

    name: Final[str] = Path(parsed.netloc.replace("www.", "")) / (parsed.path.strip("/") or "index") # type: ignore
    save_dir = SNAPSHOT_DIR_TRAJECTORY / name
    _ = save_dir.mkdir(parents=True, exist_ok=True)

    # Create a fresh Notte session for each page to avoid side-effects.
    with notte.Session(
        headless=True,
        enable_perception=False,
        viewport_width=VIEWPORT_WIDTH,
        viewport_height=VIEWPORT_HEIGHT,
    ) as session:
        obs = session.observe(url=url)

        obs_list: list[Observation] = [obs]

        agent = notte.Agent(session=session, reasoning_model='vertex_ai/gemini-2.0-flash')
        response = agent.run(task=task, url=url)

        # If response contains trajectory with multiple observations, add them to the list
        if hasattr(response, 'trajectory') and response.trajectory:
            for step in response.trajectory:
                if hasattr(step, 'obs') and isinstance(step.obs, Observation):
                    obs_list.append(step.obs)

        for i, obs in enumerate(obs_list):
            curr_step_dir = save_dir / f"step_{i}"
            _ = curr_step_dir.mkdir(parents=True, exist_ok=True)
            
            url = obs.metadata.url
            save_snapshot(curr_step_dir, session, url)


@pytest.mark.parametrize("url", urls())
def test_observe_snapshot(url: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""
    # TODO move ts
    save_snapshot_static(url)

    # actual = dump_interaction_nodes(session)
    # expected = json.loads(json_path.read_text(encoding="utf-8"))
    # if actual != expected:
    #    raise AssertionError(f"Data snapshot mismatch for {name}")