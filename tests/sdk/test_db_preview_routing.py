"""NOTTE_DB_PREVIEW_BRANCH selects a database branch for a client's requests."""

from types import SimpleNamespace
from typing import Any

import pytest
from notte_sdk.endpoints.base import BaseClient
from notte_sdk.endpoints.sessions import RemoteSession, SessionsClient
from notte_sdk.types import SessionResponse, SessionStartRequest

BRANCH = "feature/my-branch"
ENV_VAR = "NOTTE_DB_PREVIEW_BRANCH"


class MockNotteClient:
    pass


def _client(api_key: str = "test-api-key") -> BaseClient:
    return BaseClient(MockNotteClient(), None, api_key=api_key)


def _sessions_client(recording_url: str) -> SessionsClient:
    """A SessionsClient whose debug info reports ``recording_url``."""
    client = SessionsClient(MockNotteClient(), api_key="test-api-key")  # pyright: ignore [reportArgumentType]
    client.debug_info = lambda session_id: SimpleNamespace(  # pyright: ignore [reportAttributeAccessIssue]
        ws=SimpleNamespace(recording=recording_url)
    )
    return client


def _session(*, request_cdp: str | None = None, response_cdp: str | None = None, debug_cdp: str = "") -> RemoteSession:
    """A started RemoteSession with the three cdp url sources under our control.

    ``cdp_url`` prefers a caller-supplied url, then the one on the start
    response, then a debug-info lookup, so each source needs its own case.
    """
    session = object.__new__(RemoteSession)
    session.client = _client()  # pyright: ignore [reportAttributeAccessIssue]
    session.request = SessionStartRequest.model_construct(cdp_url=request_cdp)
    session.response = SessionResponse.model_construct(cdp_url=response_cdp)
    session.debug_info = lambda: SimpleNamespace(ws=SimpleNamespace(cdp=debug_cdp))  # pyright: ignore [reportAttributeAccessIssue]
    return session


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.delenv("NOTTE_DB_PREVIEW", raising=False)


def test_no_preview_header_by_default() -> None:
    assert "x-db-preview" not in _client().headers()


def test_preview_branch_is_sent_as_a_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, BRANCH)
    assert _client().headers()["x-db-preview"] == BRANCH


def test_the_shorter_variable_name_is_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console and CI both export NOTTE_DB_PREVIEW_BRANCH; only that name counts."""
    monkeypatch.setenv("NOTTE_DB_PREVIEW", BRANCH)
    assert "x-db-preview" not in _client().headers()


def test_blank_values_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "   ")
    assert "x-db-preview" not in _client().headers()


def test_branch_is_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, f"  {BRANCH}  ")
    assert _client().headers()["x-db-preview"] == BRANCH


def test_explicit_headers_still_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, BRANCH)
    headers = _client().headers({"x-db-preview": "explicit"})
    assert headers["x-db-preview"] == "explicit"


def test_websocket_url_is_unchanged_without_a_branch() -> None:
    url = "wss://api.notte.cc/agents/a/debug/logs?token=t"
    assert _client()._with_db_preview(url) == url


def test_websocket_url_carries_the_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, BRANCH)
    url = "wss://api.notte.cc/agents/a/debug/logs?token=t"
    assert (
        _client()._with_db_preview(url)
        == "wss://api.notte.cc/agents/a/debug/logs?token=t&db_preview=feature%2Fmy-branch"
    )


def test_websocket_url_without_a_query_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "main")
    assert _client()._with_db_preview("wss://api.notte.cc/ws") == "wss://api.notte.cc/ws?db_preview=main"


def test_branch_survives_a_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """The server parses this back out, so the encoding has to be recoverable."""
    from urllib.parse import parse_qsl, urlparse

    monkeypatch.setenv(ENV_VAR, "feature/a+b c")
    url = _client()._with_db_preview("wss://api.notte.cc/ws?token=t")
    assert dict(parse_qsl(urlparse(url).query))["db_preview"] == "feature/a+b c"


# The cdp url is what session.page connects to. A preview-branch session is
# unknown to the default database, so a handshake without the selector is
# rejected and every managed auth verifier fails before it reads the page.


def test_cdp_url_from_debug_info_carries_the_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, BRANCH)
    session = _session(debug_cdp="wss://api.notte.cc/sessions/s/debug?token=t")
    assert session.cdp_url() == "wss://api.notte.cc/sessions/s/debug?token=t&db_preview=feature%2Fmy-branch"


def test_cdp_url_from_the_start_response_carries_the_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, BRANCH)
    session = _session(response_cdp="wss://api.notte.cc/sessions/s/debug?token=t")
    assert session.cdp_url() == "wss://api.notte.cc/sessions/s/debug?token=t&db_preview=feature%2Fmy-branch"


def test_a_caller_supplied_cdp_url_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """That url belongs to another browser provider, not to our API."""
    monkeypatch.setenv(ENV_VAR, BRANCH)
    external = "wss://connect.browserbase.com/?apiKey=k"
    assert _session(request_cdp=external).cdp_url() == external


def test_cdp_url_is_unchanged_without_a_branch() -> None:
    url = "wss://api.notte.cc/sessions/s/debug?token=t"
    assert _session(debug_cdp=url).cdp_url() == url


def test_the_recording_stream_carries_the_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, BRANCH)
    url = "wss://api.notte.cc/sessions/s/debug/recording?token=t"
    service: Any = _sessions_client(url).viewer_notebook(session_id="s")
    assert service.wss_url == f"{url}&db_preview=feature%2Fmy-branch"


def test_the_recording_stream_is_unchanged_without_a_branch() -> None:
    url = "wss://api.notte.cc/sessions/s/debug/recording?token=t"
    service: Any = _sessions_client(url).viewer_notebook(session_id="s")
    assert service.wss_url == url
