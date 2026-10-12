from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from notte_browser.playwright_async_api import Error
from notte_browser.session import NotteSession
from notte_browser.window import BrowserWindow
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata

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


@pytest.mark.asyncio
async def test_snapshot_retry_after_playwright_error_keeps_arguments(session: NotteSession) -> None:
    calls = 0
    snapshot_metadata = BrowserWindow.snapshot_metadata

    async def flaky_metadata(self: BrowserWindow) -> SnapshotMetadata:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise Error("transient failure")
        return await snapshot_metadata(self)

    with patch.object(BrowserWindow, "snapshot_metadata", new=flaky_metadata), _no_screenshot():
        snapshot = await session.window.snapshot(screenshot=False, skip_dom=True, selector="main")

    assert calls == 2
    assert snapshot.screenshot is None
    # skip_dom is kept on retry: the dom tree is the empty root, not the parsed page
    assert len(snapshot.interaction_nodes()) == 0
    assert snapshot.html_content.startswith("<h1>Title</h1>")
