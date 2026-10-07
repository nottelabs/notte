import asyncio
import datetime as dt
import io
import json
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import notte_sdk.endpoints.agents as agents_module
import pytest
from notte_core.common.logging import logger
from notte_sdk.endpoints.agents import AgentsClient
from notte_sdk.types import AgentStatus, AgentStatusResponse
from typing_extensions import override
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close, CloseCode


class _TimeoutWebsocket:
    def __init__(self) -> None:
        self.recv_timeout: float | None = None

    def __enter__(self) -> "_TimeoutWebsocket":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def recv(self, timeout: float | None = None) -> str:
        self.recv_timeout = timeout
        raise TimeoutError


API_KEY = "test-only-secret-agent-logs-key"  # pragma: allowlist secret
VIEWER_TOKEN = "viewer.jwt.token"


def _debug_info(token: str) -> SimpleNamespace:
    return SimpleNamespace(ws=SimpleNamespace(logs=f"wss://api.notte.cc/sessions/session-id/debug/logs?token={token}"))


def _agents_client(debug_info: Callable[..., SimpleNamespace] | None = None) -> AgentsClient:
    client = object.__new__(AgentsClient)
    client.token = API_KEY
    client.db_preview = None
    client.root_client = SimpleNamespace(  # type: ignore[assignment]
        sessions=SimpleNamespace(debug_info=debug_info or (lambda session_id: _debug_info(VIEWER_TOKEN)))
    )
    client.request_path = lambda _endpoint: (  # type: ignore[method-assign]
        "https://api.notte.cc/agents/{agent_id}/debug/logs?token={token}&session_id={session_id}"
    )
    return client


@pytest.fixture
def captured_logs() -> Iterator[io.StringIO]:
    captured = io.StringIO()
    handler = logger.add(captured, level="DEBUG")
    try:
        yield captured
    finally:
        logger.remove(handler)


def _closed_agent_status(agent_id: str, session_id: str) -> AgentStatusResponse:
    return AgentStatusResponse(
        agent_id=agent_id,
        session_id=session_id,
        created_at=dt.datetime.now(dt.UTC),
        status=AgentStatus.closed,
        task="task",
        success=False,
    )


def test_watch_logs_returns_on_websocket_inactivity(monkeypatch) -> None:
    websocket = _TimeoutWebsocket()
    monkeypatch.setattr("notte_sdk.endpoints.agents.sync_client.connect", lambda **_kwargs: websocket)
    monkeypatch.setattr(
        agents_module,
        "config",
        SimpleNamespace(agent_logs_inactivity_timeout_seconds=12.5),
    )

    response = _agents_client().watch_logs(
        agent_id="agent-id",
        session_id="session-id",
        log=False,
    )

    assert response is None
    assert websocket.recv_timeout == 12.5


def test_watch_logs_and_wait_polls_status_after_websocket_inactivity(monkeypatch) -> None:
    client = _agents_client()
    monkeypatch.setattr(client, "watch_logs", lambda **_kwargs: None)
    monkeypatch.setattr(client, "status", lambda agent_id: _closed_agent_status(agent_id, "session-id"))
    monkeypatch.setattr(
        agents_module,
        "config",
        SimpleNamespace(agent_status_poll_timeout_seconds=1.0),
    )

    response = client.watch_logs_and_wait(
        agent_id="agent-id",
        session_id="session-id",
        log=False,
    )

    assert response.status == AgentStatus.closed
    assert response.agent_id == "agent-id"


class _ServiceRestartWebsocket:
    """Delivers one log event, then the server drops the socket with 1012 (service restart)."""

    def __init__(self) -> None:
        self.messages: list[str] = [json.dumps({"validation": "step validated"})]

    def __enter__(self) -> "_ServiceRestartWebsocket":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def recv(self, timeout: float | None = None) -> str:
        if self.messages:
            return self.messages.pop(0)
        raise ConnectionClosedError(Close(CloseCode.SERVICE_RESTART, "service restart"), None)


def test_watch_logs_and_wait_polls_status_after_abnormal_websocket_close(monkeypatch) -> None:
    client = _agents_client()
    websocket = _ServiceRestartWebsocket()
    status_calls: list[str] = []

    def status(agent_id: str) -> AgentStatusResponse:
        status_calls.append(agent_id)
        return _closed_agent_status(agent_id, "session-id")

    monkeypatch.setattr("notte_sdk.endpoints.agents.sync_client.connect", lambda **_kwargs: websocket)
    monkeypatch.setattr(client, "status", status)
    monkeypatch.setattr(
        agents_module,
        "config",
        SimpleNamespace(agent_logs_inactivity_timeout_seconds=12.5, agent_status_poll_timeout_seconds=1.0),
    )

    response = client.watch_logs_and_wait(
        agent_id="agent-id",
        session_id="session-id",
        log=False,
    )

    assert websocket.messages == []
    assert status_calls == ["agent-id"]
    assert response.status == AgentStatus.closed
    assert response.agent_id == "agent-id"


def test_watch_logs_still_raises_unexpected_errors(monkeypatch) -> None:
    class _BrokenWebsocket(_TimeoutWebsocket):
        @override
        def recv(self, timeout: float | None = None) -> str:
            raise RuntimeError("boom")

    monkeypatch.setattr("notte_sdk.endpoints.agents.sync_client.connect", lambda **_kwargs: _BrokenWebsocket())
    monkeypatch.setattr(
        agents_module,
        "config",
        SimpleNamespace(agent_logs_inactivity_timeout_seconds=12.5),
    )

    with pytest.raises(RuntimeError, match="boom"):
        _ = _agents_client().watch_logs(agent_id="agent-id", session_id="session-id", log=False)


class _FakeJsWebSocket:
    """Minimal stand-in for the browser WebSocket used by the Pyodide code path."""

    def __init__(self) -> None:
        self.readyState: int = 1  # OPEN
        self.listeners: dict[str, Any] = {}

    def addEventListener(self, name: str, listener: Any) -> None:
        self.listeners[name] = listener
        if name == "close":
            loop = asyncio.get_running_loop()
            _ = loop.call_soon(self.listeners["message"], SimpleNamespace(data=json.dumps({"validation": "ok"})))
            _ = loop.call_soon(listener, SimpleNamespace(code=1012, reason="service restart", wasClean=False))

    def removeEventListener(self, name: str, _listener: Any) -> None:
        _ = self.listeners.pop(name, None)

    def close(self) -> None:
        self.readyState = 3  # CLOSED


@pytest.mark.asyncio
async def test_async_watch_logs_and_wait_polls_status_after_abnormal_websocket_close(monkeypatch) -> None:
    client = _agents_client()
    ws = _FakeJsWebSocket()
    status_calls: list[str] = []

    def status(agent_id: str) -> AgentStatusResponse:
        status_calls.append(agent_id)
        return _closed_agent_status(agent_id, "session-id")

    monkeypatch.setattr(agents_module, "RUNNING_IN_PYODIDE", True)
    monkeypatch.setattr(
        agents_module, "js", SimpleNamespace(WebSocket=SimpleNamespace(new=lambda _url: ws)), raising=False
    )
    monkeypatch.setattr(agents_module, "create_proxy", lambda fn: fn, raising=False)
    monkeypatch.setattr(client, "status", status)
    monkeypatch.setattr(
        agents_module,
        "config",
        SimpleNamespace(agent_logs_inactivity_timeout_seconds=12.5, agent_status_poll_timeout_seconds=1.0),
    )

    response = await client.async_watch_logs_and_wait(
        agent_id="agent-id",
        session_id="session-id",
        log=False,
    )

    assert status_calls == ["agent-id"]
    assert response.status == AgentStatus.closed
    assert ws.listeners == {}


def test_watch_logs_authenticates_with_viewer_token_not_api_key(monkeypatch, captured_logs) -> None:
    urls: list[str] = []

    def connect(**kwargs: Any) -> _TimeoutWebsocket:
        urls.append(kwargs["uri"])
        return _TimeoutWebsocket()

    monkeypatch.setattr("notte_sdk.endpoints.agents.sync_client.connect", connect)
    monkeypatch.setattr(agents_module, "config", SimpleNamespace(agent_logs_inactivity_timeout_seconds=1.0))

    _ = _agents_client().watch_logs(agent_id="agent-id", session_id="session-id", log=False)

    assert urls == [f"wss://api.notte.cc/agents/agent-id/debug/logs?token={VIEWER_TOKEN}&session_id=session-id"]
    assert API_KEY not in captured_logs.getvalue()


@pytest.mark.parametrize("failure", ["api_key_token", "missing_token", "request_error"])
def test_watch_logs_never_puts_api_key_in_url(monkeypatch, captured_logs, failure) -> None:
    def debug_info(session_id: str) -> SimpleNamespace:
        match failure:
            case "api_key_token":
                return _debug_info(API_KEY)
            case "missing_token":
                return SimpleNamespace(ws=SimpleNamespace(logs="wss://api.notte.cc/sessions/session-id/debug/logs"))
            case _:
                raise ConnectionError(f"Request failed: {API_KEY}")

    def connect(**_kwargs: Any) -> _TimeoutWebsocket:
        raise AssertionError("must not open a websocket without a viewer token")

    monkeypatch.setattr("notte_sdk.endpoints.agents.sync_client.connect", connect)

    response = _agents_client(debug_info).watch_logs(agent_id="agent-id", session_id="session-id", log=False)

    assert response is None
    output = captured_logs.getvalue()
    assert "Falling back to status polling" in output
    assert API_KEY not in output


@pytest.mark.asyncio
async def test_async_watch_logs_authenticates_with_viewer_token_not_api_key(monkeypatch, captured_logs) -> None:
    urls: list[str] = []

    def new(url: str) -> _FakeJsWebSocket:
        urls.append(url)
        return _FakeJsWebSocket()

    monkeypatch.setattr(agents_module, "RUNNING_IN_PYODIDE", True)
    monkeypatch.setattr(agents_module, "js", SimpleNamespace(WebSocket=SimpleNamespace(new=new)), raising=False)
    monkeypatch.setattr(agents_module, "create_proxy", lambda fn: fn, raising=False)
    monkeypatch.setattr(agents_module, "config", SimpleNamespace(agent_logs_inactivity_timeout_seconds=1.0))

    _ = await _agents_client().async_watch_logs(agent_id="agent-id", session_id="session-id", log=False)

    assert urls == [f"wss://api.notte.cc/agents/agent-id/debug/logs?token={VIEWER_TOKEN}&session_id=session-id"]
    assert API_KEY not in captured_logs.getvalue()
