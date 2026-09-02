from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.sessions import RemoteSession


def _bare_session() -> RemoteSession:
    session = object.__new__(RemoteSession)
    session._playwright_browser = None
    session._playwright_context = None
    session._playwright_page = None
    session._async_playwright_browser = None
    session._async_playwright_context = None
    session._async_playwright_page = None
    session.cdp_url = MagicMock(return_value="ws://notte.example/cdp")
    return session


def _browser_with_page() -> tuple[MagicMock, MagicMock, MagicMock]:
    page = MagicMock()
    context = MagicMock()
    context.pages = [page]
    browser = MagicMock()
    browser.contexts = [context]
    return browser, context, page


def test_sync_page_makes_backend_the_native_dialog_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _bare_session()
    browser, context, page = _browser_with_page()
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp.return_value = browser
    starter = MagicMock()
    starter.start.return_value = playwright
    monkeypatch.setattr(sessions, "_playwright_available", True)
    monkeypatch.setattr(sessions, "_sync_playwright", MagicMock(return_value=starter))

    assert session.page is page

    context.on.assert_called_once_with("dialog", sessions._observe_server_owned_dialog)
    assert sessions._observe_server_owned_dialog(MagicMock()) is None


@pytest.mark.asyncio
async def test_async_page_makes_backend_the_native_dialog_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _bare_session()
    browser, context, page = _browser_with_page()
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    starter = MagicMock()
    starter.start = AsyncMock(return_value=playwright)
    monkeypatch.setattr(sessions, "_async_playwright_available", True)
    monkeypatch.setattr(sessions, "_async_playwright", MagicMock(return_value=starter))

    assert await session.apage is page

    context.on.assert_called_once_with("dialog", sessions._observe_server_owned_dialog)
    assert sessions._observe_server_owned_dialog(MagicMock()) is None
