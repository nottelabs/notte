import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.types import SessionStartRequest


def bare_session():
    session = object.__new__(RemoteSession)
    session.response = None
    session.request = SimpleNamespace(
        auth_ids=["connection"],
        cdp_url=None,
        wait_for_authentication=True,
        model_dump=lambda **kwargs: {"auth_ids": ["connection"]},
    )
    session.client = MagicMock()
    session.client.server_url = "https://api.notte.cc"
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


@pytest.mark.parametrize("failures", [1, 2, 3])
def test_start_retries_final_metadata_refresh(monkeypatch, failures):
    monkeypatch.setattr("notte_sdk.endpoints.sessions.time.sleep", lambda _: None)
    session = bare_session()
    ready = session.client.status.return_value
    session.client.status.side_effect = [requests.ConnectionError("temporary") for _ in range(failures)] + [ready]
    if failures == 3:
        with pytest.raises(requests.ConnectionError):
            session.start()
        session.stop.assert_called_once_with(close_reason="error")
        assert session.client.status.call_count == 3
    else:
        session.start()
        assert session.response is ready
        session.stop.assert_not_called()
        assert session.client.status.call_count == failures + 1
    session.client.start.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [1, 2, 3])
async def test_async_entry_retries_final_metadata_refresh(monkeypatch, failures):
    monkeypatch.setattr("notte_sdk.endpoints.sessions.asyncio.sleep", AsyncMock())
    session = bare_session()
    ready = session.client.status.return_value
    session.client.status.side_effect = [requests.ConnectionError("temporary") for _ in range(failures)] + [ready]
    if failures == 3:
        with pytest.raises(requests.ConnectionError):
            await session.__aenter__()
        session.stop.assert_called_once_with(close_reason="error")
        assert session.client.status.call_count == 3
    else:
        assert await session.__aenter__() is session
        assert session.response is ready
        session.stop.assert_not_called()
        assert session.client.status.call_count == failures + 1
    session.client.start.assert_called_once()


@pytest.mark.parametrize("asynchronous", [False, True])
def test_capability_does_not_bypass_failed_readiness(monkeypatch, asynchronous):
    monkeypatch.setenv("NOTTE_AUTH_CAPABILITY", "runner-capability")
    session = bare_session()
    session.response = SimpleNamespace(session_id="session", status="authenticating")
    session.client.auth_status.return_value = SimpleNamespace(status="failed", error="Login failed")
    with pytest.raises(RuntimeError, match="Login failed"):
        if asynchronous:
            asyncio.run(session.await_for_auth())
        else:
            session.wait_for_auth()
    session.client.auth_status.assert_called_once_with("session")


def test_cdp_capability_is_header_only_and_not_sent_to_external_provider(monkeypatch):
    from notte_sdk.endpoints.base import BaseClient

    monkeypatch.setenv("NOTTE_AUTH_CAPABILITY", "runner-capability")
    session = bare_session()
    assert session._cdp_auth_headers("wss://api.notte.cc/sessions/s/cdp") == {
        "x-notte-auth-capability": "runner-capability"
    }
    client = SimpleNamespace(db_preview=None)
    assert (
        BaseClient._with_db_preview(client, "wss://api.notte.cc/sessions/s/cdp") == "wss://api.notte.cc/sessions/s/cdp"
    )
    assert session._cdp_auth_headers("wss://external.invalid/cdp") is None
    session.request.cdp_url = "wss://external.invalid/cdp"
    assert session._cdp_auth_headers("wss://api.notte.cc/sessions/s/cdp") is None


@pytest.mark.parametrize(
    ("api_url", "cdp_url", "expected"),
    [
        ("https://api.notte.cc", "wss://api.notte.cc:443/cdp", True),
        ("https://api.notte.cc:443", "wss://api.notte.cc/cdp", True),
        ("http://localhost", "ws://localhost:80/cdp", False),
        ("http://localhost:80", "ws://localhost/cdp", False),
        ("https://api.notte.cc:8443", "wss://api.notte.cc:8443/cdp", True),
        ("https://api.notte.cc", "wss://api.notte.cc:8443/cdp", False),
        ("https://api.notte.cc", "ws://api.notte.cc:443/cdp", False),
        ("https://api.notte.cc", "wss://external.invalid:443/cdp", False),
    ],
)
def test_cdp_capability_matches_effective_origin(monkeypatch, api_url, cdp_url, expected):
    monkeypatch.setenv("NOTTE_AUTH_CAPABILITY", "runner-capability")
    session = bare_session()
    session.client.server_url = api_url
    assert session._cdp_auth_headers(cdp_url) == (
        {"x-notte-auth-capability": "runner-capability"} if expected else None
    )
