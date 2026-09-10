import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.types import SessionStartRequest


def bare_session():
    session = object.__new__(RemoteSession)
    session.response = None
    session.request = SimpleNamespace(
        auth_ids=["connection"], wait_for_authentication=True, model_dump=lambda **kwargs: {"auth_ids": ["connection"]}
    )
    session.client = MagicMock()
    session.client.start.return_value = SimpleNamespace(session_id="session", status="authenticating")
    session.client.auth_status.return_value = SimpleNamespace(status="active", error=None)
    session.client.status.return_value = SimpleNamespace(session_id="session", status="active")
    session.storage = MagicMock()
    session._open_viewer = False
    session._cookie_file = None
    session.stop = MagicMock()
    return session


def test_default_start_waits_using_readiness_without_repeating_start(monkeypatch):
    monkeypatch.setattr("notte_sdk.endpoints.sessions.time.sleep", lambda _: None)
    session = bare_session()
    session.client.auth_status.side_effect = [
        SimpleNamespace(status="authenticating"),
        SimpleNamespace(status="active"),
    ]
    session.start()
    session.client.start.assert_called_once()
    assert session.client.auth_status.call_count == 2
    assert session.response.status == "active"


def test_explicit_nonblocking_start_returns_pending_without_polling():
    session = bare_session()
    session.start(wait_for_authentication=False)
    session.client.auth_status.assert_not_called()
    assert session.response.status == "authenticating"


def test_terminal_authentication_failure_closes_without_another_start():
    session = bare_session()
    session.client.auth_status.return_value = SimpleNamespace(status="failed", error="Invalid credentials")
    with pytest.raises(RuntimeError, match="Invalid credentials"):
        session.start()
    session.client.start.assert_called_once()
    session.stop.assert_called_once_with(close_reason="error")


@pytest.mark.asyncio
async def test_async_context_waits_before_yielding():
    session = bare_session()
    session.start = MagicMock()
    session.await_for_auth = AsyncMock()
    assert await session.__aenter__() is session
    session.start.assert_called_once_with(wait_for_authentication=False)
    session.await_for_auth.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_async_wait_closes_the_started_session():
    session = bare_session()
    session.response = SimpleNamespace(session_id="session", status="authenticating")
    session.start = MagicMock()
    session.await_for_auth = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await session.__aenter__()
    session.stop.assert_called_once_with(close_reason="error")


@pytest.mark.parametrize("mode", ["python", "json"])
def test_login_retry_is_only_serialized_for_managed_auth(mode):
    assert "auth_retry" not in SessionStartRequest().model_dump(mode=mode)
    assert SessionStartRequest(auth_ids=["connection"], auth_retry=2).model_dump(mode=mode)["auth_retry"] == 2
