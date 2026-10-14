import asyncio
import traceback
from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_browser.errors import CdpConnectionError
from notte_browser.playwright import PlaywrightManager
from notte_browser.playwright_async_api import Browser, BrowserContext, Page, Playwright
from notte_browser.window import BrowserWindowOptions
from notte_sdk.types import LocalSessionStartRequest


@pytest.fixture
def browser_manager():
    playwright = MagicMock(spec=Playwright)
    browser = MagicMock(spec=Browser)
    context = MagicMock(spec=BrowserContext)
    page = MagicMock(spec=Page)
    page.url = "about:blank"
    page.context = context
    context.pages = [page]
    browser.new_context.return_value = context
    playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    playwright.chromium.launch = AsyncMock(return_value=browser)

    manager = PlaywrightManager()
    manager.set_playwright(playwright)
    return manager, playwright, browser, page


@pytest.mark.asyncio
@pytest.mark.parametrize("cdp_url", [None, "http://127.0.0.1:9222"])
async def test_new_window_connects_or_launches_browser(browser_manager, cdp_url):
    manager, playwright, browser, page = browser_manager
    options = BrowserWindowOptions.from_request(LocalSessionStartRequest(headless=True, cdp_url=cdp_url))

    window = await manager.new_window(options)

    assert window.page is page
    assert window.resource.options == options
    if cdp_url is None:
        playwright.chromium.launch.assert_awaited_once()
        playwright.chromium.connect_over_cdp.assert_not_awaited()
    else:
        playwright.chromium.connect_over_cdp.assert_awaited_once_with(cdp_url)
        playwright.chromium.launch.assert_not_awaited()
    browser.new_context.assert_awaited_once()

    await window.close()

    page.context.close.assert_awaited_once()
    browser.close.assert_awaited_once()
    playwright.stop.assert_awaited_once()
    assert not manager.is_started()


@pytest.mark.asyncio
async def test_new_window_does_not_launch_browser_when_cdp_connection_fails(browser_manager):
    manager, playwright, browser, _ = browser_manager
    options = BrowserWindowOptions.from_request(
        LocalSessionStartRequest(headless=True, cdp_url="http://127.0.0.1:9222")
    )
    connection_error = RuntimeError("Connection refused")
    playwright.chromium.connect_over_cdp.side_effect = connection_error

    with pytest.raises(CdpConnectionError) as exc_info:
        await manager.new_window(options)

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__
    playwright.chromium.launch.assert_not_awaited()
    browser.new_context.assert_not_awaited()
    # Playwright was already running before new_window(), so its owner stops it.
    playwright.stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_window_stops_playwright_it_started_when_cdp_connection_fails(monkeypatch):
    playwright = MagicMock(spec=Playwright)
    playwright.chromium.connect_over_cdp = AsyncMock(side_effect=RuntimeError("Connection refused"))
    starter = MagicMock()
    starter.start = AsyncMock(return_value=playwright)
    monkeypatch.setattr("notte_browser.playwright.async_playwright", lambda: starter)
    manager = PlaywrightManager()
    options = BrowserWindowOptions.from_request(
        LocalSessionStartRequest(headless=True, cdp_url="http://127.0.0.1:9222")
    )

    with pytest.raises(CdpConnectionError):
        await manager.new_window(options)

    playwright.stop.assert_awaited_once()
    assert not manager.is_started()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True], ids=["error", "cancellation"])
async def test_failed_context_creation_releases_the_connection(browser_manager, monkeypatch, cancelled):
    _, playwright, browser, _ = browser_manager
    starter = MagicMock()
    starter.start = AsyncMock(return_value=playwright)
    monkeypatch.setattr("notte_browser.playwright.async_playwright", lambda: starter)
    manager = PlaywrightManager()
    failure = asyncio.CancelledError() if cancelled else RuntimeError("Remote context failure")
    browser.new_context.side_effect = failure
    options = BrowserWindowOptions.from_request(
        LocalSessionStartRequest(headless=True, cdp_url="http://127.0.0.1:9222")
    )

    with pytest.raises(type(failure)):
        await manager.new_window(options)

    browser.close.assert_awaited_once()
    playwright.stop.assert_awaited_once()
    assert not manager.is_started()


@pytest.mark.asyncio
async def test_failed_page_creation_closes_only_the_new_context(browser_manager):
    manager, playwright, browser, page = browser_manager
    context = page.context
    context.pages = []
    context.new_page.side_effect = RuntimeError("Remote page failure")
    options = BrowserWindowOptions.from_request(
        LocalSessionStartRequest(headless=True, cdp_url="http://127.0.0.1:9222")
    )

    with pytest.raises(RuntimeError, match="Remote page failure"):
        await manager.new_window(options)

    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()
    # An existing Playwright owner is preserved after an unsuccessful window.
    playwright.stop.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["context", "browser"])
async def test_close_stops_driver_even_if_resource_cleanup_fails(browser_manager, stage):
    manager, playwright, browser, page = browser_manager
    options = BrowserWindowOptions.from_request(
        LocalSessionStartRequest(headless=True, cdp_url="http://127.0.0.1:9222")
    )
    window = await manager.new_window(options)
    resource = page.context if stage == "context" else browser
    resource.close.side_effect = RuntimeError("Remote cleanup failure")

    await window.close()

    page.context.close.assert_awaited_once()
    browser.close.assert_awaited_once()
    playwright.stop.assert_awaited_once()
    assert not manager.is_started()


@pytest.mark.asyncio
async def test_connection_has_a_total_deadline(browser_manager, monkeypatch):
    manager, playwright, _, _ = browser_manager
    monkeypatch.setattr(PlaywrightManager, "BROWSER_CREATION_TIMEOUT_SECONDS", 0.01)

    async def stall(*args, **kwargs):
        await asyncio.Event().wait()

    playwright.chromium.connect_over_cdp.side_effect = stall
    options = BrowserWindowOptions.from_request(
        LocalSessionStartRequest(headless=True, cdp_url="http://127.0.0.1:9222")
    )

    with pytest.raises(CdpConnectionError):
        await asyncio.wait_for(manager.new_window(options), timeout=1)

    playwright.chromium.launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_cancellation_releases_owned_driver(browser_manager, monkeypatch):
    _, playwright, browser, _ = browser_manager
    starter = MagicMock()
    starter.start = AsyncMock(return_value=playwright)
    monkeypatch.setattr("notte_browser.playwright.async_playwright", lambda: starter)
    manager = PlaywrightManager()
    entered = asyncio.Event()

    async def stall(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    browser.new_context.side_effect = stall
    options = BrowserWindowOptions.from_request(
        LocalSessionStartRequest(headless=True, cdp_url="http://127.0.0.1:9222")
    )
    task = asyncio.create_task(manager.new_window(options))
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    browser.close.assert_awaited_once()
    playwright.stop.assert_awaited_once()
    assert not manager.is_started()


@pytest.mark.asyncio
async def test_stalled_browser_cleanup_still_stops_driver(browser_manager, monkeypatch):
    manager, playwright, browser, _ = browser_manager
    monkeypatch.setattr(PlaywrightManager, "BROWSER_OPERATION_TIMEOUT_SECONDS", 0.01)
    options = BrowserWindowOptions.from_request(
        LocalSessionStartRequest(headless=True, cdp_url="http://127.0.0.1:9222")
    )
    window = await manager.new_window(options)

    async def stall(*args, **kwargs):
        await asyncio.Event().wait()

    browser.close.side_effect = stall

    await asyncio.wait_for(window.close(), timeout=1)

    playwright.stop.assert_awaited_once()
    assert not manager.is_started()


@pytest.mark.asyncio
async def test_cdp_errors_do_not_expose_authenticated_urls(browser_manager):
    manager, playwright, _, _ = browser_manager
    secret_url = "wss://provider.example.test/private-path?token=PRIVATE-TOKEN"
    playwright.chromium.connect_over_cdp.side_effect = RuntimeError(f"Could not connect to {secret_url}")
    options = BrowserWindowOptions.from_request(LocalSessionStartRequest(headless=True, cdp_url=secret_url))

    with pytest.raises(CdpConnectionError) as error:
        await manager.new_window(options)

    displayed = "".join(traceback.format_exception(error.value))
    assert "PRIVATE-TOKEN" not in displayed
    assert "private-path" not in displayed
    for message in (error.value.dev_message, error.value.user_message, error.value.agent_message):
        assert "PRIVATE-TOKEN" not in message
