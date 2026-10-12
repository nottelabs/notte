"""Golden tests: pin what observe and scrape return on saved pages, offline.

Each page in `tests/data` is opened from disk with every non-`file://` request blocked, so the
output only depends on our code. The expected output lives next to this file in `snapshots/<page>/`:

- `observe.txt`: the action space description, then one line per interaction action
  (id, type, text label, CSS and XPath selectors, iframe / shadow-root flags)
- `scrape.md`: `session.scrape()` markdown (full page)
- `scrape_main.md`: `session.scrape(only_main_content=True)` markdown
- `images.txt`: `session.scrape(only_images=True)` (one line per image; inline `data:` URLs as a hash)

A refactor of the observe / scrape pipelines must keep these files unchanged. When a change is
intended, regenerate them and review the diff:

    NOTTE_UPDATE_GOLDEN=1 uv run pytest tests/golden
"""

import difflib
import hashlib
import os
from pathlib import Path

import pytest
from notte_core.browser.observation import Observation
from patchright.async_api import Route

import notte

DATA_DIR = Path(__file__).parent.parent / "data"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
UPDATE = os.getenv("NOTTE_UPDATE_GOLDEN") == "1"

PAGES = sorted(path.relative_to(DATA_DIR) for path in DATA_DIR.rglob("*.html"))


async def _offline(route: Route) -> None:
    if route.request.url.startswith("file:"):
        await route.continue_()
    else:
        await route.abort()


def _render_observation(obs: Observation) -> str:
    lines = [obs.space.description.rstrip(), "", "# interaction actions"]
    for action in obs.space.interaction_actions:
        selector = action.selector
        lines.append(
            "\t".join(
                [
                    action.id,
                    action.type,
                    repr(action.text_label),
                    "" if selector is None else selector.css_selector,
                    "" if selector is None else selector.xpath_selector,
                    f"in_iframe={selector is not None and selector.in_iframe}",
                    f"in_shadow_root={selector is not None and selector.in_shadow_root}",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def _image_url(url: str | None) -> str:
    if url is None or not url.startswith("data:"):
        return str(url)
    media_type = url.split(",", 1)[0]
    return f"{media_type},sha256:{hashlib.sha256(url.encode()).hexdigest()[:16]}"


def _check(page: Path, name: str, actual: str) -> None:
    # Pages are opened from disk: keep the checkout location out of the snapshots.
    actual = actual.replace(str(DATA_DIR.resolve()), "<tests/data>")
    path = SNAPSHOTS_DIR / page.with_suffix("") / name
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(actual)
        return
    assert path.exists(), f"Missing golden file {path}: run with NOTTE_UPDATE_GOLDEN=1"
    expected = path.read_text()
    if actual != expected:
        diff = difflib.unified_diff(expected.splitlines(), actual.splitlines(), "expected", "actual", lineterm="", n=1)
        shown = "\n".join(list(diff)[:80])
        pytest.fail(
            f"{path.relative_to(SNAPSHOTS_DIR)} changed (run with NOTTE_UPDATE_GOLDEN=1 if intended):\n{shown}",
            pytrace=False,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("page", PAGES, ids=str)
async def test_observe_and_scrape(page: Path) -> None:
    async with notte.Session(headless=True, viewport_width=1280, viewport_height=720) as session:
        await session.window.page.route("**/*", _offline)
        _ = await session.window.page.goto(f"file://{(DATA_DIR / page).resolve()}")

        _check(page, "observe.txt", _render_observation(await session.aobserve()))
        _check(page, "scrape.md", await session.ascrape())
        _check(page, "scrape_main.md", await session.ascrape(only_main_content=True))
        images = await session.ascrape(only_images=True)
        _check(page, "images.txt", "".join(f"{image.category}\t{_image_url(image.url)}\n" for image in images))
