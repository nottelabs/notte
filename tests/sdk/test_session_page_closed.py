"""`session.page` explains a failed connection with the session's close reason."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_core.types import SessionResponse
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.sessions import AsyncRemoteSession, RemoteSession
from notte_sdk.errors import SessionClosedError

CDP_URL = "wss://notte.example/cdp"
REFUSED = Exception("WebSocket error: wss://notte.example/cdp 410 Gone")


def _status(status: str, close_reason: str | None) -> SessionResponse:
    return SessionResponse.model_validate(
        {
            "session_id": "session-1",
            "idle_timeout_minutes": 6,
            "created_at": "2026-11-20T02:15:00Z",
            "last_accessed_at": "2026-11-20T02:17:37Z",
            "status": status,
            "close_reason": close_reason,
        }
    )


def _sync_session(monkeypatch: pytest.MonkeyPatch, status: MagicMock) -> RemoteSession:
    session = object.__new__(RemoteSession)
    session.request = SimpleNamespace(cdp_url=None)
    session.client = SimpleNamespace(server_url="https://notte.example", REQUEST_ORIGIN="sdk-python")
    session._playwright_browser = None
    session._playwright_context = None
    session._playwright_page = None
    session.cdp_url = MagicMock(return_value=CDP_URL)
    session.status = status
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp.side_effect = REFUSED
    starter = MagicMock()
    starter.start.return_value = playwright
    monkeypatch.setattr(sessions, "_playwright_available", True)
    monkeypatch.setattr(sessions, "_sync_playwright", MagicMock(return_value=starter))
    return session


def _async_session(monkeypatch: pytest.MonkeyPatch, status: AsyncMock) -> AsyncRemoteSession:
    session = object.__new__(AsyncRemoteSession)
    session.request = SimpleNamespace(cdp_url=None)
    session.client = SimpleNamespace(server_url="https://notte.example", REQUEST_ORIGIN="sdk-python")
    session._async_playwright_browser = None
    session._async_playwright_context = None
    session._async_playwright_page = None
    session.cdp_url = AsyncMock(return_value=CDP_URL)
    session.status = status
    playwright = MagicMock()
    playwright.chromium.connect_over_cdp = AsyncMock(side_effect=REFUSED)
    starter = MagicMock()
    starter.start = AsyncMock(return_value=playwright)
    monkeypatch.setattr(sessions, "_async_playwright_available", True)
    monkeypatch.setattr(sessions, "_async_playwright", MagicMock(return_value=starter))
    return session


@pytest.mark.parametrize(
    ("status", "close_reason", "message"),
    [
        ("timed_out", "idle_timeout", "Session session-1 is closed: it timed out after 6 minutes without activity."),
        ("closed", "max_duration", "Session session-1 is closed: it reached its maximum duration of 15 minutes."),
        ("closed", "manual", "Session session-1 is closed: it was stopped."),
        ("error", None, "Session session-1 is closed: its status is error."),
    ],
)
def test_sync_page_of_a_closed_session(
    monkeypatch: pytest.MonkeyPatch, status: str, close_reason: str | None, message: str
) -> None:
    session = _sync_session(monkeypatch, MagicMock(return_value=_status(status, close_reason)))

    with pytest.raises(SessionClosedError) as raised:
        _ = session.page

    assert str(raised.value).startswith(message)
    assert raised.value.close_reason == close_reason
    assert raised.value.__cause__ is REFUSED
    # Handlers written for the previous RuntimeError still catch it.
    assert isinstance(raised.value, RuntimeError)


@pytest.mark.parametrize(
    "status",
    [
        MagicMock(return_value=_status("active", None)),
        MagicMock(side_effect=Exception("status unavailable")),
    ],
    ids=["active", "status unavailable"],
)
def test_sync_page_of_a_running_or_unknown_session(monkeypatch: pytest.MonkeyPatch, status: MagicMock) -> None:
    session = _sync_session(monkeypatch, status)

    with pytest.raises(RuntimeError, match="Failed to access the playwright page from CDP") as raised:
        _ = session.page

    assert not isinstance(raised.value, SessionClosedError)
    assert raised.value.__cause__ is REFUSED


@pytest.mark.asyncio
async def test_async_page_of_a_closed_session(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _async_session(monkeypatch, AsyncMock(return_value=_status("timed_out", "idle_timeout")))

    with pytest.raises(SessionClosedError, match="timed out after 6 minutes without activity") as raised:
        _ = await session.page

    assert raised.value.__cause__ is REFUSED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        AsyncMock(return_value=_status("active", None)),
        AsyncMock(side_effect=Exception("status unavailable")),
    ],
    ids=["active", "status unavailable"],
)
async def test_async_page_of_a_running_or_unknown_session(monkeypatch: pytest.MonkeyPatch, status: AsyncMock) -> None:
    session = _async_session(monkeypatch, status)

    with pytest.raises(RuntimeError, match="Failed to access the async playwright page from CDP") as raised:
        _ = await session.page

    assert not isinstance(raised.value, SessionClosedError)
    assert raised.value.__cause__ is REFUSED
