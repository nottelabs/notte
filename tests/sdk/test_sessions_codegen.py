"""Session-management wire captures written before migrating its client."""

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from notte_core import __version__
from notte_core.config import config
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import SessionResponse
from pydantic import ValidationError

from tests.sdk.test_generated_endpoints import SERVER, fake
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client
STAMP = "2026-10-13T00:00:00Z"
SESSION = dict(session_id="session", idle_timeout_minutes=3, created_at=STAMP, last_accessed_at=STAMP, status="active")
COOKIE = dict(name="test", value="value", domain="example.test", path="/", httpOnly=False)
DEFAULT_START = {
    key: value
    for key, value in {
        "browser_type": config.browser_type if config.browser_type != "chromium" else None,
        "user_agent": config.user_agent,
        "chrome_args": config.chrome_args,
        "viewport_width": config.viewport_width,
        "viewport_height": config.viewport_height,
        "cdp_url": config.cdp_url,
    }.items()
    if value is not None
}


def test_session_wire_contract(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, SESSION)
    assert client.sessions.start().session_id == "session"
    assert client.sessions.status("session").duration == dt.timedelta()
    api.payload = {"items": [SESSION], "page": 1, "page_size": 10}
    assert len(client.sessions.list()) == 1
    api.payload = {**SESSION, "status": "closed", "closed_at": STAMP}
    assert client.sessions.stop("session").status == "closed"
    api.payload = {"success": True, "message": "saved"}
    assert client.sessions.set_cookies("session", cookies=[COOKIE]).success is True
    api.payload = {"cookies": [COOKIE]}
    assert client.sessions.get_cookies("session").cookies[0].value == "value"
    api.payload = {"offset": 4}
    assert client.sessions.offset("session").offset == 4
    api.payload = {"mp4_url": "https://storage.example/replay.mp4"}
    assert client.sessions.replay("session", wait=False).mp4_url == api.payload["mp4_url"]
    api.payload = {"session_id": "session", "status": "active", "operations": []}
    assert client.sessions.auth_readiness("session").status == "active"
    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in api.calls] == [
        ("POST", "/sessions/start", {}),
        ("GET", "/sessions/session", {}),
        ("GET", "/sessions/", {}),
        ("DELETE", "/sessions/session/stop", {}),
        ("POST", "/sessions/session/cookies", {}),
        ("GET", "/sessions/session/cookies", {}),
        ("GET", "/sessions/session/offset", {}),
        ("GET", "/sessions/session/replay", {}),
        ("GET", "/sessions/session/auth", {}),
    ]
    assert json.loads(api.calls[0].data) == DEFAULT_START
    assert json.loads(api.calls[4].data) == {"cookies": [COOKIE]}
    for call in api.calls:
        assert call.headers == {
            "Authorization": "Bearer test-api-key",  # pragma: allowlist secret
            "x-notte-sdk-version": __version__,
            "x-notte-request-origin": "sdk-python",
            **({"Content-Type": "application/json"} if call.method == "POST" else {}),
        }


@pytest.mark.parametrize(
    "kwargs,extra",
    [
        ({}, {}),
        ({"timeout_minutes": 5}, {"idle_timeout_minutes": 5}),
        ({"advanced_stealth": True}, {"advanced_stealth": True}),
        ({"block_ads": False}, {"block_ads": False}),
        ({"record_session": False}, {"record_session": False}),
        ({"log_session": False}, {"log_session": False}),
        ({"record_session": False, "log_session": False}, {"record_session": False, "log_session": False}),
        ({"record_session": True, "log_session": False}, {"log_session": False}),
        ({"record_session": False, "log_session": True}, {"record_session": False}),
        ({"record_session": True, "log_session": True}, {}),
        ({"auth_ids": ["connection"], "auth_retry": 2}, {"auth_ids": ["connection"], "auth_retry": 2}),
    ],
)
def test_session_start_omission_contract(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any], extra: dict[str, Any]
) -> None:
    api = fake(monkeypatch, SESSION)
    _ = client.sessions.start(**kwargs)
    assert json.loads(api.calls[0].data) == {**DEFAULT_START, **extra}


@pytest.mark.parametrize(
    "name,args,kwargs",
    [
        ("start", (), {}),
        ("status", ("session",), {}),
        ("list", (), {}),
        ("stop", ("session",), {}),
        ("set_cookies", ("session",), {"cookies": [COOKIE]}),
        ("get_cookies", ("session",), {}),
        ("debug_info", ("session",), {}),
        ("debug_tab_info", ("session",), {"tab_idx": 1}),
        ("offset", ("session",), {}),
        ("replay", ("session",), {"wait": False}),
        ("auth_readiness", ("session",), {}),
    ],
)
@pytest.mark.parametrize("status", [404, 422])
def test_session_api_errors(
    client: NotteClient,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    args: tuple[str, ...],
    kwargs: dict[str, Any],
    status: int,
) -> None:
    api = fake(monkeypatch, {"detail": "session error"}, status)
    with pytest.raises(NotteAPIError) as error:
        getattr(client.sessions, name)(*args, **kwargs)
    assert error.value.status_code == status
    assert len(api.calls) == 1


@pytest.mark.parametrize(
    "values", [{"timeout_minutes": 7}, {"idle_timeout_minutes": 5}, {"idle_timeout_minutes": 5, "timeout_minutes": 7}]
)
def test_response_timeout_alias_precedence(values: dict[str, int]) -> None:
    data = {key: value for key, value in SESSION.items() if key != "idle_timeout_minutes"}
    response = SessionResponse.model_validate({**data, **values})
    expected = values.get("idle_timeout_minutes", values.get("timeout_minutes"))
    assert response.idle_timeout_minutes == expected
    assert response.model_dump()["timeout_minutes"] == expected
    assert response.steps == []


@pytest.mark.parametrize(
    "data",
    [
        {"viewport_width": 400},
        {"proxies": [{"type": "unknown"}]},
        {"auth_retry": 3},
        {"auth_ids": ["connection", "connection"]},
        {"headless": False},
        {"advanced_stealth": True, "cdp_url": "wss://external.test"},
        {"cdp_url": "wss://external.test", "proxies": True},
        {"aspect_ratio": "invalid"},
        {"idle_timeout_minutes": 20, "max_duration_minutes": 10},
    ],
)
@pytest.mark.parametrize("high_level", [False, True])
def test_invalid_start_values_reach_api(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, data: dict[str, Any], high_level: bool
) -> None:
    api = fake(monkeypatch, {"detail": "invalid session input"}, 422)
    with pytest.raises(NotteAPIError) as error:
        if high_level:
            client.Session(**data).start(tries=1)
        else:
            client.sessions.start(**data)
    assert error.value.status_code == 422
    assert len(api.calls) == 1
    body = json.loads(api.calls[0].data)
    assert all(body[key] == value for key, value in data.items())


@pytest.mark.parametrize(
    "cookie", [{**COOKIE, "sameSite": "invalid"}, {"name": "missing-fields"}, {**COOKIE, "expires": None}]
)
def test_cookie_inputs_reach_api(client: NotteClient, monkeypatch: pytest.MonkeyPatch, cookie: Any) -> None:
    api = fake(monkeypatch, {"detail": "invalid cookie"}, 422)
    with pytest.raises(NotteAPIError) as error:
        client.sessions.set_cookies("session", cookies=[cookie])
    assert error.value.status_code == 422
    assert json.loads(api.calls[0].data) == {"cookies": [cookie]}


@pytest.mark.parametrize(
    "data",
    [
        {"auth_ids": [f"connection-{i}" for i in range(11)]},
        {"max_duration_minutes": 1441},
        {"proxies": [{"extra_customer_arg": "test"}]},
        {"auth_ids": None},
    ],
)
def test_additional_validation_is_owned_by_api(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, data: dict[str, Any]
) -> None:
    api = fake(monkeypatch, {"detail": "invalid input"}, 422)
    with pytest.raises(NotteAPIError) as error:
        client.sessions.start(**data)
    assert error.value.status_code == 422
    body = json.loads(api.calls[0].data)
    assert all(body[key] == value for key, value in data.items())


def test_auth_operation_response_compatibility(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_sdk.types import ManagedAuthOperation

    operation = dict(
        id="operation", connection_id="connection", source="session", status="succeeded", phase="done", deadline=STAMP
    )
    api = fake(monkeypatch, dict(session_id="session", status="active", operations=[operation]))
    result = client.sessions.auth_readiness("session")
    assert isinstance(result.operations[0], ManagedAuthOperation)
    assert result.operations[0].attempt == 0
    api.payload = operation
    assert isinstance(client.managed_auth.get_operation("operation"), ManagedAuthOperation)


def test_cookie_file_preserves_raw_input(client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from notte_sdk.types import Cookie, SetCookiesRequest

    values = [{**COOKIE, "domain": "https://www.example.test/path", "sameSite": "invalid", "custom": "value"}]
    path = tmp_path / "cookies.json"
    _ = path.write_text(json.dumps(values))
    assert SetCookiesRequest.from_json(path).model_dump() == {"cookies": values}
    # Local loading still validates, so an invalid sameSite never reaches a browser.
    with pytest.raises(ValidationError):
        _ = Cookie.from_json(path)
    api = fake(monkeypatch, {"detail": "invalid cookie"}, 422)
    with pytest.raises(NotteAPIError) as error:
        client.sessions.set_cookies("session", cookie_file=path)
    assert error.value.status_code == 422
    assert json.loads(api.calls[0].data) == {"cookies": values}


def test_session_request_alias_precedence(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, SESSION)
    _ = client.sessions.start(**dict(idle_timeout_minutes=5, timeout_minutes=7))
    body = json.loads(api.calls[0].data)
    assert body["idle_timeout_minutes"] == 5
    assert "timeout_minutes" not in body


def test_debug_response_and_legacy_tab(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_core.snapshot import TabsData
    from notte_sdk.types import TabSessionDebugResponse

    tab = dict(
        metadata=dict(tab_id=1, title="test", url="https://example.test"),
        debug_url="https://debug.test",
        ws_url="wss://tab.test",
    )
    api = fake(
        monkeypatch,
        dict(
            debug_url="https://debug.test",
            ws=dict(cdp="wss://cdp.test", recording="wss://record.test", logs="wss://log.test"),
            tabs=[tab],
        ),
    )
    response = client.sessions.debug_info("s/one?#")
    assert isinstance(response.tabs[0], TabSessionDebugResponse)
    assert isinstance(response.tabs[0].metadata, TabsData)
    assert api.calls[0].url == SERVER + "/sessions/s%2Fone%3F%23/debug"
    api.payload = tab
    assert isinstance(client.sessions.debug_tab_info("session", tab_idx=1), TabSessionDebugResponse)
    assert api.calls[-1].params == {"tab_idx": "1"}
    assert api.calls[-1].url == SERVER + "/sessions/session/debug/tab"


def test_debug_websocket_type_matches_public_import(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_sdk.types import WebSocketUrls

    _ = fake(
        monkeypatch,
        dict(
            debug_url="https://debug.test",
            ws=dict(cdp="wss://cdp.test", recording="wss://record.test", logs="wss://log.test"),
            tabs=[],
        ),
    )
    response = client.sessions.debug_info("session")
    assert isinstance(response.ws, WebSocketUrls)


@pytest.mark.parametrize(
    "name,value",
    [
        ("user_agent", "configured-agent"),
        ("chrome_args", ["--configured"]),
        ("viewport_width", 1200),
        ("viewport_height", 800),
        ("cdp_url", "wss://configured.test"),
    ],
)
def test_explicit_null_clears_configured_start_default(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, name: str, value: Any
) -> None:
    from notte_sdk.types import SessionStartRequest

    monkeypatch.setattr(SessionStartRequest.model_fields[name], "default", value)
    api = fake(monkeypatch, SESSION)
    browser = client.Session(**{name: None})
    browser.start(tries=1)
    assert name not in json.loads(api.calls[0].data)


def test_start_model_dump_honors_selection() -> None:
    from notte_sdk.types import SessionStartRequest

    request = SessionStartRequest.from_data(
        dict(
            cdp_url="wss://external.test", proxies=[dict(type="external", server="http://proxy.test", username="user")]
        )
    )
    assert request.model_dump(include={"cdp_url"}) == {"cdp_url": "wss://external.test"}
    assert "cdp_url" not in request.model_dump(exclude={"cdp_url"})
    assert request.model_dump(include={"proxies": {0: {"server"}}}) == {"proxies": [{"server": "http://proxy.test"}]}


@pytest.mark.parametrize("options", [{"exclude_unset": True}, {"exclude_defaults": True}])
def test_start_model_dump_honors_default_selection(options: dict[str, bool]) -> None:
    from notte_sdk.types import SessionStartRequest

    request = SessionStartRequest.from_data({"user_agent": "explicit-agent"})
    assert request.model_dump(**options) == {"user_agent": "explicit-agent"}
    assert "cdp_url" not in request.model_dump(exclude_none=True)
    assert json.loads(request.model_dump_json(include={"user_agent"})) == {"user_agent": "explicit-agent"}


@pytest.mark.parametrize("options", [{"exclude_unset": True}, {"exclude_defaults": True}])
def test_start_model_dump_excludes_nested_model_defaults(options: dict[str, bool]) -> None:
    from notte_sdk.types import SessionProfile, SessionStartRequest

    request = SessionStartRequest.from_data({"profile": SessionProfile(id="profile")})
    assert request.model_dump(**options) == {"profile": {"id": "profile"}}


def test_country_proxy_helper_keeps_public_enum() -> None:
    from notte_sdk.types import NotteProxy, ProxyGeolocationCountry

    proxy = NotteProxy.from_country("fr")
    assert proxy.country is ProxyGeolocationCountry.FRANCE
    assert proxy.country.value == "fr"
    assert NotteProxy.from_country("invalid").model_dump(mode="json")["country"] == "invalid"


def test_cookie_file_keeps_public_cookie_objects(tmp_path: Path) -> None:
    from notte_sdk.types import Cookie, SetCookiesRequest

    path = tmp_path / "cookies.json"
    _ = path.write_text(json.dumps([COOKIE]))
    cookie = SetCookiesRequest.from_json(path).cookies[0]
    assert isinstance(cookie, Cookie)
    assert cookie.domain == "example.test"
    assert cookie.model_dump(exclude_unset=True) == COOKIE


def test_remote_session_keeps_nested_request_objects(client: NotteClient) -> None:
    from notte_sdk.types import ExternalProxy, NotteProxy, ProxyGeolocationCountry, SessionProfile, TailnetProxy

    session = client.Session(
        profile={"id": "profile"},
        proxies=[
            {"type": "notte", "country": "fr"},
            {"type": "external", "server": "http://proxy.test"},
            {"type": "tailnet", "exit_node": "device"},
        ],
    )
    assert isinstance(session.request.profile, SessionProfile)
    assert session.request.profile.id == "profile"
    assert isinstance(session.request.proxies, list)
    first, second, third = session.request.proxies
    assert isinstance(first, NotteProxy)
    assert first.country is ProxyGeolocationCountry.FRANCE
    assert isinstance(second, ExternalProxy)
    assert second.server == "http://proxy.test"
    assert isinstance(third, TailnetProxy)
    assert third.exit_node == "device"


def test_remote_session_country_shorthand_keeps_proxy_object(client: NotteClient) -> None:
    from notte_sdk.types import NotteProxy, ProxyGeolocationCountry

    request = client.Session(proxies="fr").request
    assert isinstance(request.proxies, list)
    assert isinstance(request.proxies[0], NotteProxy)
    assert request.proxies[0].country is ProxyGeolocationCountry.FRANCE


def test_remote_session_external_proxy_conversion(client: NotteClient) -> None:
    request = client.Session(proxies=[{"type": "external", "server": "http://proxy.test"}]).request
    assert request.playwright_proxy == {
        "server": "http://proxy.test",
        "username": None,
        "password": None,
        "bypass": None,
    }


def test_session_string_fields_keep_runtime_string_behavior() -> None:
    response = SessionResponse.model_validate({**SESSION, "status": "closed", "close_reason": "manual"})
    assert type(response.status) is str
    assert response.status == "closed"
    assert type(response.browser_type) is str
    assert response.browser_type == "chromium"
    assert response.close_reason == "manual"


def test_session_start_omits_matching_api_defaults(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_sdk.types import SessionStartRequest

    for name in ("browser_type", "user_agent", "chrome_args", "viewport_width", "viewport_height", "cdp_url"):
        monkeypatch.setattr(
            SessionStartRequest.model_fields[name], "default", "chromium" if name == "browser_type" else None
        )
    api = fake(monkeypatch, SESSION)
    _ = client.sessions.start()
    assert json.loads(api.calls[0].data) == {}


def test_cookie_export_keeps_deprecation_and_round_trip(tmp_path: Path) -> None:
    from notte_sdk.types import Cookie

    path = tmp_path / "cookies.json"
    cookie = Cookie.model_validate(COOKIE)
    with pytest.warns(DeprecationWarning, match="Cookie.dump_json"):
        written = Cookie.dump_json([cookie], path)
    assert written == len(path.read_text())
    assert json.loads(path.read_text()) == [cookie.model_dump()]
    assert Cookie.from_json(path)[0].name == cookie.name


def test_local_cookie_file_keeps_expiry_from_expiration_date(tmp_path: Path) -> None:
    from notte_sdk.types import Cookie

    path = tmp_path / "cookies.json"
    _ = path.write_text(json.dumps([{**COOKIE, "expirationDate": 1_900_000_000.0}]))
    cookie = Cookie.from_json(path)[0]
    assert cookie.expires == 1_900_000_000.0
