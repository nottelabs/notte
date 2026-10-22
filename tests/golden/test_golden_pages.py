"""Golden tests: pin what observe and scrape return on saved pages, offline.

Each page in `tests/data` is served from disk at `http://golden.test/<page>` without its `<script>`
and `<iframe>` elements, and every other request is blocked, so the output only depends on our code.
The saved pages' own scripts would otherwise rebuild parts of the DOM on each run, and iframes are
listed in a different order between runs (and serialised differently across platforms when their
`srcdoc` is malformed), so iframe handling is not covered here.

The expected output lives next to this file in `snapshots/<page>/`:

- `observe.txt`: the action space description, then one line per interaction action
  (id, type, text label, accessible name, CSS and XPath selectors, iframe / shadow-root flags)
- `scrape.md`: `session.scrape()` markdown (full page)
- `scrape_main.md`: `session.scrape(only_main_content=True)` markdown

A refactor of the observe / scrape pipelines must keep these files unchanged. When a change is
intended, regenerate them and review the diff:

    NOTTE_UPDATE_GOLDEN=1 uv run pytest tests/golden
"""

import difflib
import os
from pathlib import Path

import pytest
from lxml import html as lxml_html
from notte_core.observation import Observation
from patchright.async_api import Route

import notte

DATA_DIR = Path(__file__).parent.parent / "data"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
UPDATE = os.getenv("NOTTE_UPDATE_GOLDEN") == "1"
BASE_URL = "http://golden.test/"

PAGES = sorted(path.relative_to(DATA_DIR) for path in DATA_DIR.rglob("*.html"))


def _static_html(path: Path) -> str:
    document = lxml_html.document_fromstring(path.read_text())
    for element in document.xpath("//script | //iframe"):
        element.drop_tree()
    return lxml_html.tostring(document, encoding="unicode", doctype="<!DOCTYPE html>")


async def _serve(route: Route) -> None:
    request = route.request
    if request.resource_type != "document" or not request.url.startswith(BASE_URL):
        await route.abort()
        return
    path = DATA_DIR / request.url.removeprefix(BASE_URL)
    if not path.is_file():
        await route.abort()
        return
    await route.fulfill(body=_static_html(path), content_type="text/html; charset=utf-8")


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
                    repr(action.accessible_name),
                    "" if selector is None else selector.css_selector,
                    "" if selector is None else selector.xpath_selector,
                    f"in_iframe={selector is not None and selector.in_iframe}",
                    f"in_shadow_root={selector is not None and selector.in_shadow_root}",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def _check(page: Path, name: str, actual: str) -> None:
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
        await session.window.page.route("**/*", _serve)
        _ = await session.window.page.goto(f"{BASE_URL}{page.as_posix()}")

        _check(page, "observe.txt", _render_observation(await session.aobserve()))
        _check(page, "scrape.md", await session.ascrape())
        _check(page, "scrape_main.md", await session.ascrape(only_main_content=True))
