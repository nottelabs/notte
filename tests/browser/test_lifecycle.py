from unittest.mock import AsyncMock, MagicMock

import notte_browser.playwright as lifecycle
import pytest
from notte_browser.driver import Browser, BrowserContext, Page, Playwright, async_playwright
from notte_browser.errors import BrowserNotAvailableError, CdpConnectionError
from notte_browser.session import NotteSession
from notte_browser.window import BrowserWindowOptions
from notte_core.types import LocalSessionStartRequest


def _options(**kwargs) -> BrowserWindowOptions:
    return BrowserWindowOptions.from_request(LocalSessionStartRequest(headless=True, **kwargs))


def _driver(monkeypatch: pytest.MonkeyPatch):
    driver = MagicMock(spec=Playwright)
    browser = MagicMock(spec=Browser)
    context = MagicMock(spec=BrowserContext)
    page = MagicMock(spec=Page)
    page.url = "about:blank"
    page.context = context
    context.pages = [page]
    browser.contexts = [context]
    browser.new_context.return_value = context
    driver.chromium.launch = AsyncMock(return_value=browser)
    driver.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    monkeypatch.setattr(lifecycle, "_start_driver", AsyncMock(return_value=driver))
    return driver, browser, context, page


@pytest.mark.asyncio
async def test_launch_owns_browser_and_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, browser, context, page = _driver(monkeypatch)
    options = _options(viewport_width=800, viewport_height=600, user_agent="test-agent")
    window = await lifecycle.launch(options)
    assert window.page is page and window.options is options
    assert getattr(window.on_close, "__self__", None) is window
    driver.chromium.launch.assert_awaited_once()
    context_args = browser.new_context.call_args.kwargs
    assert context_args["viewport"] == {"width": 800, "height": 600}
    assert context_args["user_agent"] == "test-agent"
    assert context_args["permissions"] == ["clipboard-read", "clipboard-write"]
    events: list[str] = []
    browser.close.side_effect = lambda: events.append("browser")
    driver.stop.side_effect = lambda: events.append("driver")
    await window.close()
    assert events == ["browser", "driver"]
    page.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_reuses_context_and_only_disconnects(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, browser, context, page = _driver(monkeypatch)
    window = await lifecycle.connect("http://localhost:9222")
    assert window.page is page
    assert window.options.cdp_url == "http://localhost:9222"
    driver.chromium.connect_over_cdp.assert_awaited_once_with("http://localhost:9222")
    browser.new_context.assert_not_awaited()
    context.set_extra_http_headers.assert_not_awaited()
    await window.close()
    driver.stop.assert_awaited_once()
    browser.close.assert_not_awaited()
    context.close.assert_not_awaited()
    page.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_cdp_url_routes_through_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, browser, _, _ = _driver(monkeypatch)
    async with NotteSession(cdp_url="http://localhost:9222", headless=True):
        driver.chromium.connect_over_cdp.assert_awaited_once_with("http://localhost:9222")
        driver.chromium.launch.assert_not_awaited()
    driver.stop.assert_awaited_once()
    browser.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_launch_context_failure_releases_browser_and_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, browser, _, _ = _driver(monkeypatch)
    browser.new_context.side_effect = RuntimeError("context failed")
    with pytest.raises(RuntimeError, match="context failed"):
        await lifecycle.launch(_options())
    browser.close.assert_awaited_once()
    driver.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_unsupported_launch_releases_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, browser, _, _ = _driver(monkeypatch)
    with pytest.raises(BrowserNotAvailableError):
        await lifecycle.launch(_options(browser_type="firefox"))
    driver.stop.assert_awaited_once()
    browser.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_failure_releases_only_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, browser, _, _ = _driver(monkeypatch)
    driver.chromium.connect_over_cdp.side_effect = RuntimeError("connect failed")
    with pytest.raises(CdpConnectionError):
        await lifecycle.connect("http://localhost:9222")
    driver.stop.assert_awaited_once()
    browser.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_failure_still_stops_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, browser, _, _ = _driver(monkeypatch)
    window = await lifecycle.launch(_options())
    browser.close.side_effect = RuntimeError("close failed")
    await window.close()
    driver.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_cdp_session_disconnect_leaves_caller_browser_open() -> None:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(
            channel="chromium", headless=True, args=[f"--remote-debugging-port={port}"]
        )
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content("<title>Borrowed browser</title><button>Stay open</button>")
            async with NotteSession(cdp_url=f"http://127.0.0.1:{port}", headless=True) as session:
                assert await session.page.title() == "Borrowed browser"
            assert browser.is_connected()
            assert not page.is_closed()
            assert await page.title() == "Borrowed browser"
        finally:
            await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{"X-Requested-By": "backend"}, {}])
async def test_session_cdp_applies_explicit_headers_to_reused_context(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
) -> None:
    _, browser, context, _ = _driver(monkeypatch)
    async with NotteSession(cdp_url="http://localhost:9222", headless=True, extra_http_headers=headers):
        context.set_extra_http_headers.assert_awaited_once_with(headers)
        browser.new_context.assert_not_awaited()
