import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from notte_browser.driver import async_playwright
from notte_browser.errors import PlaywrightError
from notte_browser.window import BrowserWindow, BrowserWindowOptions
from notte_core.errors import SnapshotProcessingError
from notte_core.snapshot import SnapshotMetadata, ViewportData
from notte_sdk.types import LocalSessionStartRequest


def window() -> SimpleNamespace:
    metadata = SnapshotMetadata(
        title="Fixture",
        url="https://example.com",
        tabs=[],
        viewport=ViewportData(
            scroll_x=0, scroll_y=0, viewport_width=800, viewport_height=600, total_width=800, total_height=600
        ),
    )
    return SimpleNamespace(
        page=SimpleNamespace(url=metadata.url, content=AsyncMock(return_value="<main>unchanged</main>")),
        screenshot=AsyncMock(return_value=b"image"),
        snapshot_metadata=AsyncMock(return_value=metadata),
        goto_response=None,
    )


@pytest.mark.asyncio
async def test_explicit_html_snapshot_skips_image_without_retry() -> None:
    target = window()
    snapshot = await BrowserWindow.snapshot(target, skip_dom=True, screenshot=False)
    assert snapshot.html_content == "<main>unchanged</main>"
    assert snapshot.screenshot is None
    target.screenshot.assert_not_awaited()
    target.page.content.assert_awaited_once()


@pytest.mark.asyncio
async def test_default_snapshot_still_captures_image_after_html() -> None:
    target = window()
    order = []

    async def content():
        order.append("html")
        return "<main>unchanged</main>"

    async def image():
        order.append("image")
        return b"image"

    target.page.content.side_effect = content
    target.screenshot.side_effect = image
    snapshot = await BrowserWindow.snapshot(target, skip_dom=True)
    assert snapshot.screenshot == b"image"
    assert order == ["html", "image"]


@pytest.mark.asyncio
async def test_html_snapshot_retries_keep_capture_capability() -> None:
    target = window()
    target.long_wait = AsyncMock()
    target.page.content.side_effect = [
        SnapshotProcessingError(url="https://example.com", dev_message="retry"),
        "<main>unchanged</main>",
    ]
    target.snapshot = lambda **kwargs: BrowserWindow.snapshot(target, **kwargs)
    snapshot = await target.snapshot(skip_dom=True, screenshot=False)
    assert snapshot.screenshot is None
    assert snapshot.html_content == "<main>unchanged</main>"
    target.screenshot.assert_not_awaited()
    assert target.page.content.await_count == 2


@pytest.mark.asyncio
async def test_real_html_capture_matches_image_bearing_capture() -> None:
    html = '<main><h1>Ready content</h1><p>Unicode café, €42, −3.5%</p><a href="/doc">Document</a></main>'
    async with async_playwright() as playwright:
        executable = os.getenv("NOTTE_TEST_CHROMIUM_EXECUTABLE") or playwright.chromium.executable_path
        if not Path(executable).is_file():
            pytest.skip("Chromium is not installed")
        browser = await playwright.chromium.launch(executable_path=executable, headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(html)
            target = BrowserWindow(
                page=page, options=BrowserWindowOptions.from_request(LocalSessionStartRequest(headless=True))
            )
            legacy = await target.snapshot(skip_dom=True)
            candidate = await target.snapshot(skip_dom=True, screenshot=False)
            assert candidate.html_content == legacy.html_content
            assert candidate.dom_node == legacy.dom_node
            assert candidate.metadata.url == legacy.metadata.url
            assert candidate.screenshot is None
            assert legacy.screenshot
        finally:
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["navigation", "metadata"])
async def test_other_retries_preserve_html_only_capture(stage: str) -> None:
    target = window()
    target.short_wait = AsyncMock()
    target.page.wait_for_timeout = AsyncMock()
    target.snapshot = lambda **kwargs: BrowserWindow.snapshot(target, **kwargs)
    if stage == "navigation":
        target.page.content.side_effect = [
            RuntimeError("Unable to retrieve content because the page is navigating and changing the content"),
            "<main>unchanged</main>",
        ]
    else:
        target.snapshot_metadata.side_effect = [
            PlaywrightError[0]("metadata changed"),
            target.snapshot_metadata.return_value,
        ]
    snapshot = await target.snapshot(skip_dom=True, screenshot=False)
    assert snapshot.html_content == "<main>unchanged</main>"
    assert snapshot.screenshot is None
    target.screenshot.assert_not_awaited()
    assert target.page.content.await_count == 2
