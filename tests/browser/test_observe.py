import datetime as dt
import json
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

import pytest
from notte_core import __version__
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
    return ["https://allrecipes.com", "https://x.com"]


class SnapshotMetadata(BaseModel):
    url: str
    created_at: str = Field(default_factory=lambda: dt.datetime.now().isoformat())
    version: str = __version__


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
                "selectors": selectors,
            }
        )

    return nodes_dump


def generate_offline_snapshot(url: str) -> None:
    parsed = urlparse(url)

    parsed.query
    name = Path(parsed.netloc) / (parsed.path.strip("/") or "index")
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
        name = urlparse(url).netloc
        save_dir = SNAPSHOT_DIR / name
        _ = save_dir.mkdir(parents=True, exist_ok=True)

        with open(save_dir / "metadata.json", "w") as fp:
            json.dump(SnapshotMetadata(url=url).model_dump(), fp, indent=2, ensure_ascii=False)

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


@pytest.mark.parametrize("url", urls())
def test_observe_snapshot(url: str) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""

    generate_offline_snapshot(url)

    # actual = dump_interaction_nodes(session)
    # expected = json.loads(json_path.read_text(encoding="utf-8"))
    # if actual != expected:
    #    raise AssertionError(f"Data snapshot mismatch for {name}")
