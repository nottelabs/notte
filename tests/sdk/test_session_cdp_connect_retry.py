"""`session.page` retries a CDP connection once when it drops before the WebSocket upgrade."""

import socket
import threading
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.sessions import AsyncRemoteSession, RemoteSession
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

CDP_URL = "wss://notte.example/s/token"

# First lines and call logs as Playwright 1.64 reports them.
HANG_UP = Exception(
    "BrowserType.connect_over_cdp: WebSocket error: socket hang up\nCall log:\n"
    "  - <ws connect error> wss://notte.example/s/token socket hang up\n"
    "  - <ws disconnected> wss://notte.example/s/token code=1006 reason="
)
TRANSPORT_FAILURES = [
    HANG_UP,
    Exception("BrowserType.connect_over_cdp: WebSocket error: read ECONNRESET"),
    Exception("BrowserType.connect_over_cdp: WebSocket error: connect ECONNREFUSED 127.0.0.1:443"),
    Exception("BrowserType.connect_over_cdp: WebSocket error: connect ETIMEDOUT 10.0.0.1:443"),
    Exception(
        "BrowserType.connect_over_cdp: WebSocket error: "
        "Client network socket disconnected before secure TLS connection was established"
    ),
]


def _http_answer(status: str, body: str) -> Exception:
    return Exception(
        f"BrowserType.connect_over_cdp: WebSocket error: wss://notte.example/s/token {status}\n{body}\nCall log:\n"
        f"  - <ws unexpected response> wss://notte.example/s/token {status}\n"
        "  - <ws connect error> wss://notte.example/s/token socket hang up\n"
        "  - <ws disconnected> wss://notte.example/s/token code=1006 reason="
    )


NOT_RETRIED = [
    _http_answer("403 Forbidden", "Session URL expired"),
    _http_answer("403 Forbidden", "InvalidRoutingToken"),
    _http_answer("410 Gone", ""),
    _http_answer("503 Service Unavailable", "connection limit reached, ECONNREFUSED"),
    Exception(
        "BrowserType.connect_over_cdp: WebSocket error: wss://notte.example/ECONNRESET/s/token 403 Forbidden\n"
        "Session URL expired"
    ),
    Exception("BrowserType.connect_over_cdp: Timeout 30000ms exceeded.\nCall log:\n  - <ws connecting> wss://x"),
]


@pytest.fixture(autouse=True)
def no_delay(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setattr(sessions, "CDP_CONNECT_RETRY_DELAY", 0)
    logger = MagicMock()
    monkeypatch.setattr(sessions, "logger", logger)
    return logger


def _sync_session(monkeypatch: pytest.MonkeyPatch, connect: MagicMock) -> RemoteSession:
    session = object.__new__(RemoteSession)
    session.request = SimpleNamespace(cdp_url=None)
    session.client = SimpleNamespace(server_url="https://notte.example", REQUEST_ORIGIN="sdk-python")
    session._playwright_browser = None
    session._playwright_context = None
    session._playwright_page = None
    session.cdp_url = MagicMock(return_value=CDP_URL)
    session.status = MagicMock(side_effect=Exception("status unavailable"))
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = connect
    starter = MagicMock()
    starter.start.return_value = playwright
    monkeypatch.setattr(sessions, "_playwright_available", True)
    monkeypatch.setattr(sessions, "_sync_playwright", MagicMock(return_value=starter))
    return session


def _async_session(monkeypatch: pytest.MonkeyPatch, connect: AsyncMock) -> AsyncRemoteSession:
    session = object.__new__(AsyncRemoteSession)
    session.request = SimpleNamespace(cdp_url=None)
    session.client = SimpleNamespace(server_url="https://notte.example", REQUEST_ORIGIN="sdk-python")
    session._async_playwright_browser = None
    session._async_playwright_context = None
    session._async_playwright_page = None
    session.cdp_url = AsyncMock(return_value=CDP_URL)
    session.status = AsyncMock(side_effect=Exception("status unavailable"))
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = connect
    starter = MagicMock()
    starter.start = AsyncMock(return_value=playwright)
    monkeypatch.setattr(sessions, "_async_playwright_available", True)
    monkeypatch.setattr(sessions, "_async_playwright", MagicMock(return_value=starter))
    return session


def _browser() -> MagicMock:
    browser = MagicMock()
    browser.contexts = [MagicMock(pages=[MagicMock(name="page")])]
    return browser


@pytest.mark.parametrize("failure", TRANSPORT_FAILURES, ids=str)
def test_sync_page_retries_a_transport_failure_once(
    monkeypatch: pytest.MonkeyPatch, no_delay: MagicMock, failure: Exception
) -> None:
    browser = _browser()
    connect = MagicMock(side_effect=[failure, browser])
    session = _sync_session(monkeypatch, connect)

    page = session.page

    assert page is browser.contexts[0].pages[0]
    assert connect.call_count == 2
    # The retry reuses the URL and the headers of the first attempt.
    assert connect.call_args_list[0] == connect.call_args_list[1]
    assert connect.call_args_list[1].args == (CDP_URL,)
    no_delay.warning.assert_called_once()
    assert "token" not in no_delay.warning.call_args.args[0]


def test_sync_page_retries_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = MagicMock(side_effect=[HANG_UP, HANG_UP, _browser()])
    session = _sync_session(monkeypatch, connect)

    with pytest.raises(RuntimeError, match="Failed to access the playwright page from CDP") as raised:
        _ = session.page

    assert connect.call_count == 2
    assert raised.value.__cause__ is HANG_UP


@pytest.mark.parametrize("failure", NOT_RETRIED, ids=lambda e: str(e).partition("\n")[0])
def test_sync_page_does_not_retry_an_http_answer_or_a_timeout(
    monkeypatch: pytest.MonkeyPatch, no_delay: MagicMock, failure: Exception
) -> None:
    connect = MagicMock(side_effect=[failure, _browser()])
    session = _sync_session(monkeypatch, connect)

    with pytest.raises(RuntimeError, match="Failed to access the playwright page from CDP") as raised:
        _ = session.page

    assert connect.call_count == 1
    assert raised.value.__cause__ is failure
    no_delay.warning.assert_not_called()


@pytest.mark.asyncio
async def test_async_page_retries_a_transport_failure_once(
    monkeypatch: pytest.MonkeyPatch, no_delay: MagicMock
) -> None:
    browser = _browser()
    connect = AsyncMock(side_effect=[HANG_UP, browser])
    session = _async_session(monkeypatch, connect)

    page = await session.page

    assert page is browser.contexts[0].pages[0]
    assert connect.await_count == 2
    assert connect.call_args_list[0] == connect.call_args_list[1]
    no_delay.warning.assert_called_once()


@pytest.mark.asyncio
async def test_async_page_retries_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = AsyncMock(side_effect=[HANG_UP, HANG_UP, _browser()])
    session = _async_session(monkeypatch, connect)

    with pytest.raises(RuntimeError, match="Failed to access the async playwright page from CDP") as raised:
        _ = await session.page

    assert connect.await_count == 2
    assert raised.value.__cause__ is HANG_UP


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", NOT_RETRIED, ids=lambda e: str(e).partition("\n")[0])
async def test_async_page_does_not_retry_an_http_answer_or_a_timeout(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    connect = AsyncMock(side_effect=[failure, _browser()])
    session = _async_session(monkeypatch, connect)

    with pytest.raises(RuntimeError, match="Failed to access the async playwright page from CDP"):
        _ = await session.page

    assert connect.await_count == 1


def _server(handler: Callable[[socket.socket], None]) -> Iterator[str]:
    listener = socket.create_server(("127.0.0.1", 0))

    def accept() -> None:
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                _ = connection.recv(65536)
                handler(connection)

    threading.Thread(target=accept, daemon=True).start()
    yield f"ws://127.0.0.1:{listener.getsockname()[1]}/s/token"
    listener.close()


def _hang_up(_connection: socket.socket) -> None:
    """Close the connection without answering the upgrade request."""


def _forbidden(connection: socket.socket) -> None:
    body = b"Session URL expired"
    connection.sendall(
        b"HTTP/1.1 403 Forbidden\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body)
    )


@pytest.mark.parametrize(("handler", "retried"), [(_hang_up, True), (_forbidden, False)], ids=["hang up", "403"])
def test_real_playwright_errors_are_classified(handler: Callable[[socket.socket], None], retried: bool) -> None:
    """The classifier reads the errors Playwright actually raises, against a local server."""
    server = _server(handler)
    url = next(server)
    try:
        with sync_playwright() as p, pytest.raises(PlaywrightError) as raised:
            _ = p.chromium.connect_over_cdp(url, timeout=10_000)
    finally:
        _ = next(server, None)

    assert "code=1006" in str(raised.value)
    assert (sessions._cdp_transport_failure(raised.value) is not None) is retried  # pyright: ignore [reportPrivateUsage]
