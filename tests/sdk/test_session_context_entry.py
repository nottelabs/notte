"""`with client.Session()` stops a session its entry created when the entry then fails.

Python does not call `__exit__` when `__enter__` raises, so without this the remote browser
keeps running until its idle timeout.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from notte_core.logging import logger
from notte_sdk import NotteClient
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.errors import NotteAPIError

from tests.sdk.test_generated_endpoints import SERVER, Call, FakeSession
from tests.sdk.test_sessions_codegen import COOKIE, SESSION, STAMP
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client
CLOSED = {**SESSION, "status": "closed", "closed_at": STAMP}
START = ("POST", "/sessions/start")
STOP = ("DELETE", "/sessions/session/stop")
SET_COOKIES = ("POST", "/sessions/session/cookies")
GET_COOKIES = ("GET", "/sessions/session/cookies")
AUTH = ("GET", "/sessions/session/auth")


class RoutedFake(FakeSession):
    """A `FakeSession` that answers each method and path with its own status and payload."""

    def __init__(self, routes: dict[tuple[str, str], tuple[int, Any]]) -> None:
        super().__init__(None)
        self.routes: dict[tuple[str, str], tuple[int, Any]] = routes

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.status_code, self.payload = self.routes[(request.method, request.url.path)]
        return super()._handle(request)

    def stops(self) -> list[Call]:
        return [call for call in self.calls if (call.method, call.url.removeprefix(SERVER)) == STOP]


def routed(monkeypatch: pytest.MonkeyPatch, **overrides: tuple[int, Any]) -> RoutedFake:
    routes = {
        START: (200, SESSION),
        SET_COOKIES: (200, {"success": True, "message": "saved"}),
        GET_COOKIES: (200, {"cookies": [COOKIE]}),
        STOP: (200, CLOSED),
    }
    named = {"start": START, "stop": STOP, "set_cookies": SET_COOKIES, "auth": AUTH}
    routes.update({named[name]: response for name, response in overrides.items()})
    api = RoutedFake(routes)
    monkeypatch.setattr("notte_sdk._transport.SharedHttpClient.get", lambda _: api.client)
    return api


def cookie_file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "cookies.json"
    _ = path.write_text(content)
    return path


def test_invalid_cookie_file_stops_the_created_session(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = routed(monkeypatch)
    path = cookie_file(tmp_path, "{not json")
    with pytest.raises(json.JSONDecodeError):
        with client.Session(cookie_file=path):
            pytest.fail("the body must not run")
    assert [call.params for call in api.stops()] == [{"close_reason": "error"}]
    # Saving cookies on stop could not merge into the invalid file and left it as it was.
    assert path.read_text() == "{not json"


def test_cookie_upload_error_stops_the_created_session(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = routed(monkeypatch, set_cookies=(422, {"detail": "invalid cookie"}))
    path = cookie_file(tmp_path, json.dumps([COOKIE]))
    with pytest.raises(NotteAPIError) as error:
        with client.Session(cookie_file=path):
            pytest.fail("the body must not run")
    assert error.value.status_code == 422
    assert [call.params for call in api.stops()] == [{"close_reason": "error"}]
    # The stop saved the browser's cookies, as on any error exit.
    assert [(c.method, c.url.removeprefix(SERVER)) for c in api.calls] == [START, SET_COOKIES, GET_COOKIES, STOP]


def test_interrupted_entry_stops_the_created_session(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = routed(monkeypatch)

    def interrupt(*_: Any, **__: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(RemoteSession, "set_cookies", interrupt)
    with pytest.raises(KeyboardInterrupt):
        with client.Session(cookie_file=cookie_file(tmp_path, json.dumps([COOKIE]))):
            pytest.fail("the body must not run")
    assert [call.params for call in api.stops()] == [{"close_reason": "error"}]


def test_failed_stop_keeps_the_original_error(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = routed(monkeypatch, stop=(400, {"detail": "stop failed"}))
    records: list[str] = []
    handler = logger.add(lambda message: records.append(message.record["message"]), level="ERROR")
    try:
        with pytest.raises(json.JSONDecodeError):
            with client.Session(cookie_file=cookie_file(tmp_path, "{not json")):
                pytest.fail("the body must not run")
    finally:
        logger.remove(handler)
    assert len(api.stops()) == 1
    assert any("stop failed" in record for record in records)


def test_failed_create_sends_no_stop(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = routed(monkeypatch, start=(422, {"detail": "invalid request"}))
    with pytest.raises(NotteAPIError):
        with client.Session():
            pytest.fail("the body must not run")
    assert [(c.method, c.url.removeprefix(SERVER)) for c in api.calls] == [START]


def test_attached_session_is_not_stopped_when_entry_fails(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = routed(monkeypatch)
    api.routes[("GET", "/sessions/session")] = (200, SESSION)
    session = client.Session("session")
    with pytest.raises(ValueError, match="already started"):
        with session:
            pytest.fail("the body must not run")
    assert api.stops() == []


def test_failed_authentication_stops_the_session_once(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = routed(
        monkeypatch,
        start=(200, {**SESSION, "status": "authenticating"}),
        auth=(200, {"session_id": "session", "status": "failed", "error": "Login failed", "operations": []}),
    )
    with pytest.raises(RuntimeError, match="Login failed"):
        with client.Session():
            pytest.fail("the body must not run")
    assert [call.params for call in api.stops()] == [{"close_reason": "error"}]


def test_successful_entry_is_unchanged(client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = routed(monkeypatch)
    ran = False
    with client.Session(cookie_file=cookie_file(tmp_path, json.dumps([COOKIE]))) as session:
        ran = True
        assert [(c.method, c.url.removeprefix(SERVER)) for c in api.calls] == [START, SET_COOKIES]
    assert ran
    assert session.response is not None and session.response.status == "closed"
    assert [call.params for call in api.stops()] == [{"close_reason": "manual"}]


def test_body_error_still_stops_with_error(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = routed(monkeypatch)
    with pytest.raises(RuntimeError, match="body failed"):
        with client.Session():
            raise RuntimeError("body failed")
    assert [call.params for call in api.stops()] == [{"close_reason": "error"}]
