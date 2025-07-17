import asyncio
import datetime as dt
import json
import re
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

import pytest
from notte_core import __version__
from notte_core.actions import InteractionAction
from pydantic import BaseModel, Field

import notte

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
DOM_REPORTS_DIR: Final[Path] = Path(__file__).parent.parent.parent / ".dom_reports"
SNAPSHOT_DIR: Final[Path] = DOM_REPORTS_DIR / "snapshots"
_ = SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


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

    return nodes_dump


def extract_selector(locator_str: str) -> str | None:
    match = re.search(r"selector='([^']+)'", locator_str)
    return match.group(1) if match else None


async def dump_action_resolution_reports(
    session: notte.Session, actions: Sequence[InteractionAction]
) -> list[ActionResolutionReport]:
    action_resolution_reports: list[ActionResolutionReport] = []
    for action in actions:
        locator = await session.locate(action)
        action_resolution_reports.append(
            ActionResolutionReport(
                action_id=action.id,
                locator=extract_selector(str(locator)) if locator is not None else None,
                error=None,
                success=locator is not None,
            )
        )
    return action_resolution_reports


def generate_offline_snapshot(url: str) -> None:
    parsed = urlparse(url)

    parsed.query
    name: Final[str] = Path(parsed.netloc.replace("www.", "")) / (parsed.path.strip("/") or "index")
    save_dir = SNAPSHOT_DIR / name
    _ = save_dir.mkdir(parents=True, exist_ok=True)

    # Create a fresh Notte session for each page to avoid side-effects.
    with notte.Session(
        headless=True,
        enable_perception=False,
        viewport_width=VIEWPORT_WIDTH,
        viewport_height=VIEWPORT_HEIGHT,
    ) as session:
        # obs = session.observe(url=f"file://{html_file.name}")
        obs = session.observe(url=url)
        # save page as html
        # save node dump
        # save screenshot with bourding boxes
        # => all in _
        # create new directory : _SNAPSHOT_DIR / name
        save_dir = SNAPSHOT_DIR / name
        _ = save_dir.mkdir(parents=True, exist_ok=True)

        with open(save_dir / "metadata.json", "w") as fp:
            json.dump(SnapshotMetadata(url=url).model_dump(), fp, indent=2, ensure_ascii=False)

        with open(save_dir / "actions.json", "w") as fp:
            json.dump(
                [action.model_dump() for action in obs.space.interaction_actions], fp, indent=2, ensure_ascii=False
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
            raise AssertionError(f"Screenshot is None for {name}")
        image.save(save_dir / "screenshot.png")

        # check locate interaction nodes
        with open(save_dir / "locator_reports.json", "w") as fp:
            reports: list[ActionResolutionReport] = asyncio.run(
                dump_action_resolution_reports(session, obs.space.interaction_actions)
            )
            json.dump([report.model_dump() for report in reports], fp, indent=2, ensure_ascii=False)


@pytest.mark.parametrize("url", urls())
def test_observe_snapshot(url: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""

    generate_offline_snapshot(url)

    # actual = dump_interaction_nodes(session)
    # expected = json.loads(json_path.read_text(encoding="utf-8"))
    # if actual != expected:
    #    raise AssertionError(f"Data snapshot mismatch for {name}")
