import weakref
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from notte_core import __version__ as notte_core_version
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.sessions import RemoteSession

CDP_URL = "wss://notte.example/cdp"
SDK_HEADERS = {"x-notte-request-origin": "sdk-python", "x-notte-sdk-version": notte_core_version}


def _bare_session() -> RemoteSession:
    session = object.__new__(RemoteSession)
    session.request = SimpleNamespace(cdp_url=None)
    session.client = SimpleNamespace(server_url="https://notte.example", REQUEST_ORIGIN="sdk-python")
    session._playwright_browser = None
    session._playwright_context = None
    session._playwright_page = None
    session._async_playwright_browser = None
    session._async_playwright_context = None
    session._async_playwright_page = None
    session._playwright_connection_generation = 0
    session._playwright_observed_pages = weakref.WeakSet()
    session._playwright_observed_contexts = weakref.WeakSet()
    session._playwright_cleanup_in_progress = False
    session.response = MagicMock(session_id="session-id")
    session.cdp_url = MagicMock(return_value=CDP_URL)
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
    monkeypatch.delenv("NOTTE_AUTH_CAPABILITY", raising=False)

    assert session.page is page

    playwright.chromium.connect_over_cdp.assert_called_once_with(CDP_URL, headers=SDK_HEADERS)

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
    monkeypatch.delenv("NOTTE_AUTH_CAPABILITY", raising=False)

    assert await session.apage is page

    playwright.chromium.connect_over_cdp.assert_awaited_once_with(CDP_URL, headers=SDK_HEADERS)

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


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://user@example.com:8443/cb?code=secret#token=secret", "https://example.com:8443/cb"),
        ("http://example.com/path", "http://example.com/path"),
        ("about:blank", "about:blank"),
        ("data:text/html,<p>secret</p>", "data:"),
        ("", "<redacted>"),
    ],
)
def test_redact_playwright_url(url: str, expected: str) -> None:
    assert sessions._redact_playwright_url(url) == expected


@pytest.fixture
def captured_logs() -> Iterator[list[tuple[str, str]]]:
    records: list[tuple[str, str]] = []
    handler_id = sessions.logger.add(
        lambda message: records.append((message.record["level"].name, message.record["message"])),
        level="DEBUG",
    )
    try:
        yield records
    finally:
        sessions.logger.remove(handler_id)


def test_lifecycle_log_does_not_contain_url_secrets(captured_logs: list[tuple[str, str]]) -> None:
    session = _bare_session()
    browser, _context, page = _browser_with_page()
    page.url = "https://example.com/callback?code=secret-code#access_token=secret-token"
    page.is_closed.return_value = False
    browser.is_connected.return_value = False

    session._log_playwright_event("sdk_playwright_browser_disconnected", browser=browser, cached_page=page)

    [(level, message)] = captured_logs
    assert level == "WARNING"
    assert "https://example.com/callback" in message
    assert "secret" not in message


def test_lifecycle_warnings_are_debug_during_sdk_cleanup(captured_logs: list[tuple[str, str]]) -> None:
    session = _bare_session()
    browser, _context, page = _browser_with_page()
    session._playwright_cleanup_in_progress = True

    session._log_playwright_event("sdk_playwright_browser_disconnected", browser=browser, cached_page=page)
    session._log_playwright_event(
        "sdk_playwright_session_stop_requested", browser=browser, cached_page=page, level="info"
    )

    assert [level for level, _ in captured_logs] == ["DEBUG", "INFO"]


def test_only_cached_page_close_is_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
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
    other_page = MagicMock()
    page_callback = next(call.args[1] for call in context.on.call_args_list if call.args[0] == "page")
    page_callback(other_page)
    next(call.args[1] for call in other_page.on.call_args_list if call.args[0] == "close")(other_page)
    next(call.args[1] for call in page.on.call_args_list if call.args[0] == "close")(page)

    closes = [call for call in log_event.call_args_list if call.args[0] == "sdk_playwright_page_closed"]
    assert [call.kwargs["observed_page"] for call in closes] == [other_page, page]
    assert [call.kwargs["level"] for call in closes] == ["info", "warning"]


@pytest.mark.asyncio
@pytest.mark.parametrize("use_async", [False, True])
async def test_context_exit_snapshots_state_before_closing_browser(use_async: bool) -> None:
    session = _bare_session()
    browser, _context, page = _browser_with_page()
    if use_async:
        browser.close = AsyncMock()
        session._async_playwright_browser = browser
        session._async_playwright_page = page
    else:
        session._playwright_browser = browser
        session._playwright_page = page
    session.stop = MagicMock()
    order: list[str] = []
    session._log_playwright_event = MagicMock(side_effect=lambda event, **_: order.append(event))
    browser.close.side_effect = lambda: order.append("browser_closed")

    if use_async:
        await session.__aexit__(None, None, None)
    else:
        session.__exit__(None, None, None)

    assert order == ["sdk_playwright_session_stop_requested", "browser_closed"]
    assert session._playwright_cleanup_in_progress is True


def test_failed_stop_keeps_reporting_failures_as_warnings() -> None:
    session = _bare_session()
    session._cookie_file = None
    session.client = MagicMock()
    session.client.stop.side_effect = RuntimeError("network down")

    with pytest.raises(RuntimeError, match="network down"):
        session.stop()

    assert session._playwright_cleanup_in_progress is False


def test_already_stopped_session_counts_as_cleanup() -> None:
    session = _bare_session()
    session._cookie_file = None
    session.client = MagicMock()
    session.client.stop.side_effect = RuntimeError("Session already stopped")

    session.stop()

    assert session._playwright_cleanup_in_progress is True


def test_new_tab_is_instrumented_even_when_its_id_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    # A closed page's id() can be handed to a later tab; observation must not key on it.
    monkeypatch.setattr(sessions, "id", lambda _value: 1, raising=False)
    session = _bare_session()
    browser, _context, first_page = _browser_with_page()
    second_page = MagicMock()

    session._observe_playwright_page(browser, first_page, is_async=False)
    session._observe_playwright_page(browser, second_page, is_async=False)
    session._observe_playwright_page(browser, second_page, is_async=False)

    for page in (first_page, second_page):
        assert [call.args[0] for call in page.on.call_args_list] == ["close", "crash"]
