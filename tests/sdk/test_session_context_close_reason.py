from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_sdk.endpoints.sessions import RemoteSession, SessionsClient
from notte_sdk.types import SessionStopRequest


def _bare_session() -> RemoteSession:
    session = object.__new__(RemoteSession)
    session._playwright_browser = None
    session._playwright_context = None
    session._playwright_page = None
    session._async_playwright_browser = None
    session._async_playwright_context = None
    session._async_playwright_page = None
    session.stop = MagicMock()
    return session


def test_stop_endpoint_sends_error_close_reason() -> None:
    endpoint = SessionsClient._session_stop_endpoint(
        session_id="session-id",
        params=SessionStopRequest(close_reason="error"),
    )

    assert endpoint.params is not None
    assert endpoint.params.model_dump() == {"close_reason": "error"}


def test_sync_context_exception_stops_session_as_error() -> None:
    session = _bare_session()

    session.__exit__(RuntimeError, RuntimeError("callback failed"), None)

    session.stop.assert_called_once_with(close_reason="error")


@pytest.mark.asyncio
async def test_async_context_exception_stops_session_as_error() -> None:
    session = _bare_session()
    browser = AsyncMock()
    session._async_playwright_browser = browser

    await session.__aexit__(RuntimeError, RuntimeError("callback failed"), None)

    session.stop.assert_called_once_with(close_reason="error")
    browser.close.assert_awaited_once()
