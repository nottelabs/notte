import datetime as dt
from types import SimpleNamespace

import notte_sdk.endpoints.agents as agents_module
from notte_sdk.endpoints.agents import AgentsClient
from notte_sdk.types import AgentStatus, AgentStatusResponse


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


def _agents_client() -> AgentsClient:
    client = object.__new__(AgentsClient)
    client.token = "token"
    client.request_path = lambda _endpoint: (  # type: ignore[method-assign]
        "https://api.notte.cc/agents/{agent_id}/debug/logs?token={token}&session_id={session_id}"
    )
    return client


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
