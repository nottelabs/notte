from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_browser.window import BrowserWindow
from notte_core.browser.snapshot import BrowserSnapshot

import notte

HTML = "<main><h1>Title</h1><button>Click</button></main>"


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with notte.Session(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{HTML}")
        yield session


def _no_screenshot():
    return patch.object(BrowserWindow, "screenshot", new=AsyncMock(side_effect=AssertionError("unexpected screenshot")))


@pytest.mark.asyncio
async def test_snapshot_takes_screenshot_by_default(session: NotteSession) -> None:
    snapshot = await session.window.snapshot()

    assert snapshot.screenshot is not None and len(snapshot.screenshot) > 0


@pytest.mark.asyncio
async def test_snapshot_skips_screenshot_when_not_requested(session: NotteSession) -> None:
    with _no_screenshot():
        snapshot = await session.window.snapshot(screenshot=False)

    assert snapshot.screenshot is None
    assert "Title" in snapshot.html_content
    assert len(snapshot.interaction_nodes()) == 1


@pytest.mark.asyncio
async def test_scrape_does_not_take_a_screenshot(session: NotteSession) -> None:
    with _no_screenshot():
        markdown = await session.ascrape()

    assert "Title" in markdown


@pytest.mark.asyncio
async def test_observe_keeps_screenshot_when_page_changed_during_listing(session: NotteSession) -> None:
    # force the "snapshot changed since the beginning of the listing" path, whose check snapshot has no screenshot
    with (
        patch.object(NotteSession, "nb_seconds_between_snapshots_check", -1),
        patch.object(BrowserSnapshot, "compare_with", return_value=False),
    ):
        obs = await session.aobserve()

    assert len(obs.screenshot.raw) > 0
    assert session.snapshot.screenshot == obs.screenshot.raw
