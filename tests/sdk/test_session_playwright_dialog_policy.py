from unittest.mock import ANY, AsyncMock, MagicMock

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
    session._playwright_connection_generation = 0
    session._playwright_observed_pages = set()
    session._playwright_observed_contexts = set()
    session._playwright_cleanup_in_progress = False
    session.response = MagicMock(session_id="session-id")
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

    context.on.assert_any_call("dialog", sessions._observe_server_owned_dialog)
    context.on.assert_any_call("page", ANY)
    context.on.assert_any_call("close", ANY)
    page.on.assert_any_call("close", ANY)
    page.on.assert_any_call("crash", ANY)
    browser.on.assert_called_once_with("disconnected", ANY)
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

    context.on.assert_any_call("dialog", sessions._observe_server_owned_dialog)
    context.on.assert_any_call("page", ANY)
    context.on.assert_any_call("close", ANY)
    page.on.assert_any_call("close", ANY)
    page.on.assert_any_call("crash", ANY)
    browser.on.assert_called_once_with("disconnected", ANY)
    assert sessions._observe_server_owned_dialog(MagicMock()) is None


def test_sync_page_lifecycle_callbacks_capture_state(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _bare_session()
    browser, context, page = _browser_with_page()
    page.url = "https://example.com"
    page.is_closed.return_value = False
    browser.is_connected.return_value = True
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp.return_value = browser
    starter = MagicMock()
    starter.start.return_value = playwright
    monkeypatch.setattr(sessions, "_playwright_available", True)
    monkeypatch.setattr(sessions, "_sync_playwright", MagicMock(return_value=starter))
    log_event = MagicMock()
    session._log_playwright_event = log_event

    assert session.page is page

    close_callback = next(call.args[1] for call in page.on.call_args_list if call.args[0] == "close")
    crash_callback = next(call.args[1] for call in page.on.call_args_list if call.args[0] == "crash")
    disconnect_callback = browser.on.call_args.args[1]
    context_close_callback = next(call.args[1] for call in context.on.call_args_list if call.args[0] == "close")
    close_callback(page)
    crash_callback(page)
    context_close_callback(context)
    disconnect_callback(browser)

    assert [call.args[0] for call in log_event.call_args_list] == [
        "sdk_playwright_connected",
        "sdk_playwright_page_closed",
        "sdk_playwright_page_crashed",
        "sdk_playwright_context_closed",
        "sdk_playwright_browser_disconnected",
    ]


def test_cached_page_logs_when_it_is_no_longer_live(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _bare_session()
    browser, _context, page = _browser_with_page()
    session._playwright_browser = browser
    session._playwright_page = page
    browser.is_connected.return_value = True
    page.is_closed.return_value = True
    monkeypatch.setattr(sessions, "_playwright_available", True)
    log_event = MagicMock()
    session._log_playwright_event = log_event

    assert session.page is page

    log_event.assert_called_once_with(
        "sdk_playwright_cached_page_unhealthy",
        browser=browser,
        cached_page=page,
    )


def test_new_page_callback_is_instrumented(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _bare_session()
    browser, context, page = _browser_with_page()
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp.return_value = browser
    starter = MagicMock()
    starter.start.return_value = playwright
    monkeypatch.setattr(sessions, "_playwright_available", True)
    monkeypatch.setattr(sessions, "_sync_playwright", MagicMock(return_value=starter))
    log_event = MagicMock()
    session._log_playwright_event = log_event

    assert session.page is page
    new_page = MagicMock()
    page_callback = next(call.args[1] for call in context.on.call_args_list if call.args[0] == "page")
    page_callback(new_page)

    new_page.on.assert_any_call("close", ANY)
    new_page.on.assert_any_call("crash", ANY)
    assert log_event.call_args_list[-1].args[0] == "sdk_playwright_page_created"
