import datetime as dt
import json
from typing import Final
from urllib.parse import urlparse

import pytest
from anyio import Path
from notte_core import __version__
from pydantic import BaseModel, Field

import notte

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

_REF_DIR: Final[Path] = Path(__file__).parent
_HTML_DIR: Final[Path] = _REF_DIR / "browser_snapshot"
_JSON_DIR: Final[Path] = _REF_DIR / "json_snapshot"
_ = _JSON_DIR.mkdir(parents=True, exist_ok=True)

_SNAPSHOT_DIR: Final[Path] = Path(__file__).parent / "snapshots"
_ = _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------------------
# Public helpers
# -----------------------------------------------------------------------------


def list_html_files() -> list[Path]:
    paths = sorted(_HTML_DIR.glob("*.html"))
    return [Path(p) for p in paths]


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
    name = urlparse(url).netloc
    save_dir = _SNAPSHOT_DIR / name
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
        save_dir = _SNAPSHOT_DIR / name
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


@pytest.mark.parametrize("html_file", list_html_files())
def test_observe_snapshot(html_file: Path) -> None:
    """Validate that current browser_snapshot HTML files match stored JSON snapshots."""

    name = html_file.stem

    json_path = _JSON_DIR / f"{name}.json"
    if not json_path.exists():
        raise AssertionError(f"JSON snapshot not found for {name}")

    with notte.Session(
        headless=True,
        enable_perception=False,
        viewport_width=VIEWPORT_WIDTH,
        viewport_height=VIEWPORT_HEIGHT,
    ) as session:
        _ = session.observe(url=f"file://{html_file.name}")

        actual = dump_interaction_nodes(session)

    expected = json.loads(json_path.read_text(encoding="utf-8"))

    if actual != expected:
        raise AssertionError(f"Data snapshot mismatch for {name}")
