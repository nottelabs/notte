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

    assert exc_info.value.__cause__ is connection_error
    playwright.chromium.launch.assert_not_awaited()
    browser.new_context.assert_not_awaited()
