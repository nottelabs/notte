import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.sessions import RemoteSession


@pytest.fixture(autouse=True)
def playwright_available(monkeypatch):
    monkeypatch.setattr(sessions, "_playwright_available", True)
    monkeypatch.setattr(sessions, "_async_playwright_available", True)


def binding():
    page = MagicMock()
    browser = MagicMock()
    browser.contexts = [MagicMock(pages=[page])]
    browser.is_connected.return_value = True
    return browser, page


def session_with_disconnected_client():
    session = object.__new__(RemoteSession)
    session._playwright_reconnect_lock = asyncio.Lock()
    session._playwright_context = MagicMock()
    session._playwright_browser, session._playwright_page = binding()
    session._playwright_browser.is_connected.return_value = False
    session._async_playwright_context = MagicMock()
    session._async_playwright_browser, session._async_playwright_page = binding()
    session._async_playwright_browser.is_connected.return_value = False
    session.cdp_url = MagicMock(return_value="ws://existing-session/debug")
    session.start = MagicMock()
    session.stop = MagicMock()
    return session


def test_reconnect_replaces_binding_without_replaying_or_stopping():
    session = session_with_disconnected_client()
    old_browser, old_page = session._playwright_browser, session._playwright_page
    fresh, page = binding()
    session._playwright_context.chromium.connect_over_cdp.return_value = fresh

    assert session.reconnect(timeout_ms=1500) is page
    assert session._playwright_page is page
    assert session._playwright_browser is fresh
    session._playwright_context.chromium.connect_over_cdp.assert_called_once_with(
        "ws://existing-session/debug", timeout=1500
    )
    old_browser.close.assert_not_called()
    assert not old_page.mock_calls
    assert not page.mock_calls
    session.start.assert_not_called()
    session.stop.assert_not_called()
    fresh.contexts[0].on.assert_called_once()
    # A second request reuses the healthy connection.
    assert session.reconnect() is page
    session._playwright_context.chromium.connect_over_cdp.assert_called_once()


def test_failed_handshake_preserves_binding_and_can_be_attempted_again():
    session = session_with_disconnected_client()
    old_browser, old_page = session._playwright_browser, session._playwright_page
    fresh, page = binding()
    error = RuntimeError("handshake failed")
    session._playwright_context.chromium.connect_over_cdp.side_effect = [error, fresh]
    with pytest.raises(RuntimeError, match="handshake failed"):
        session.reconnect()
    assert session._playwright_browser is old_browser
    assert session._playwright_page is old_page
    session._playwright_context.chromium.connect_over_cdp.assert_called_once()
    assert session.reconnect() is page


def test_missing_page_releases_new_connection_without_replacing_old_binding():
    session = session_with_disconnected_client()
    old = session._playwright_browser
    fresh = MagicMock(contexts=[])
    session._playwright_context.chromium.connect_over_cdp.return_value = fresh
    with pytest.raises(IndexError):
        session.reconnect()
    fresh.close.assert_called_once()
    assert session._playwright_browser is old
    session.stop.assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_does_not_connect(timeout):
    session = session_with_disconnected_client()
    with pytest.raises(ValueError):
        session.reconnect(timeout_ms=timeout)
    session.cdp_url.assert_not_called()


def test_uninitialized_sync_binding_is_rejected():
    session = session_with_disconnected_client()
    session._playwright_context = None
    with pytest.raises(RuntimeError, match="Initialize session.page"):
        session.reconnect()
    session.cdp_url.assert_not_called()


@pytest.mark.asyncio
async def test_async_concurrent_reconnects_make_one_connection_without_replay():
    session = session_with_disconnected_client()
    old_browser, old_page = session._async_playwright_browser, session._async_playwright_page
    fresh, page = binding()

    async def connect(*args, **kwargs):
        await asyncio.sleep(0)
        return fresh

    connector = AsyncMock(side_effect=connect)
    session._async_playwright_context.chromium.connect_over_cdp = connector
    assert await asyncio.gather(session.areconnect(), session.areconnect()) == [page, page]
    connector.assert_awaited_once_with("ws://existing-session/debug", timeout=10_000)
    assert session._async_playwright_browser is fresh
    assert session._async_playwright_page is page
    old_browser.close.assert_not_called()
    assert not old_page.mock_calls
    assert not page.mock_calls
    session.start.assert_not_called()
    session.stop.assert_not_called()


@pytest.mark.asyncio
async def test_async_failed_handshake_preserves_binding_and_releases_lock():
    session = session_with_disconnected_client()
    old = session._async_playwright_browser
    fresh, page = binding()
    session._async_playwright_context.chromium.connect_over_cdp = AsyncMock(
        side_effect=[RuntimeError("handshake failed"), fresh]
    )
    with pytest.raises(RuntimeError, match="handshake failed"):
        await session.areconnect()
    assert session._async_playwright_browser is old
    assert await session.areconnect() is page


@pytest.mark.asyncio
async def test_async_missing_page_releases_new_connection():
    session = session_with_disconnected_client()
    old = session._async_playwright_browser
    fresh = MagicMock(contexts=[])
    fresh.close = AsyncMock()
    session._async_playwright_context.chromium.connect_over_cdp = AsyncMock(return_value=fresh)
    with pytest.raises(IndexError):
        await session.areconnect()
    fresh.close.assert_awaited_once()
    assert session._async_playwright_browser is old
    session.stop.assert_not_called()


@pytest.mark.asyncio
async def test_async_cancellation_does_not_replace_binding_or_hold_lock():
    session = session_with_disconnected_client()
    old = session._async_playwright_browser
    started = asyncio.Event()

    async def connect(*args, **kwargs):
        started.set()
        await asyncio.Future()

    session._async_playwright_context.chromium.connect_over_cdp = AsyncMock(side_effect=connect)
    task = asyncio.create_task(session.areconnect())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert session._async_playwright_browser is old
    assert not session._playwright_reconnect_lock.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
async def test_async_invalid_timeout_does_not_connect(timeout):
    session = session_with_disconnected_client()
    with pytest.raises(ValueError):
        await session.areconnect(timeout_ms=timeout)
    session.cdp_url.assert_not_called()
