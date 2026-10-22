import datetime as dt
import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from notte_core import __version__ as notte_core_version
from notte_core.actions import BrowserAction, ClickAction
from notte_core.observation import ExecutionResult, Observation
from notte_core.space import SpaceCategory
from notte_sdk.client import NotteClient
from notte_sdk.endpoints.base import NotteEndpoint
from notte_sdk.errors import AuthenticationError
from notte_sdk.types import (
    DEFAULT_SESSION_IDLE_TIMEOUT_IN_MINUTES,
    DEFAULT_SESSION_MAX_DURATION_IN_MINUTES,
    ExecutionRequest,
    ExecutionRequestDict,
    LocalSessionStartRequest,
    ObserveResponse,
    SessionListRequest,
    SessionResponse,
    SessionStartRequest,
    SessionStartRequestDict,
    VaultListRequest,
)

from tests.sdk.test_generated_endpoints import FakeSession, fake


@pytest.fixture
def api_key() -> str:
    return "test-api-key"


@pytest.fixture
def client(api_key: str) -> NotteClient:
    return NotteClient(
        api_key=api_key,
    )


@pytest.fixture
def headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "x-notte-sdk-version": notte_core_version,
        "x-notte-request-origin": "sdk-python",
    }


@pytest.fixture
def mock_response() -> MagicMock:
    return MagicMock()


def test_client_initialization_with_env_vars() -> None:
    client = NotteClient(api_key="test-api-key")
    assert client.sessions.token == "test-api-key"


def test_client_initialization_with_params() -> None:
    client = NotteClient(api_key="custom-api-key")
    assert client.sessions.token == "custom-api-key"


def test_client_initialization_without_api_key() -> None:
    with patch.dict(os.environ, clear=True), patch("notte_sdk.auth.get_keyring_api_key", return_value=None):
        with pytest.raises(AuthenticationError):
            _ = NotteClient()


def test_base_client_accepts_empty_success_response(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, None, 204)
    result = client.sessions._request(NotteEndpoint(path="empty", response=SessionResponse, method="GET"))

    assert result == {}
    assert len(api.calls) == 1


@pytest.fixture
def session_id() -> str:
    return "test-session-123"


def session_response_dict(session_id: str, close: bool = False) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "idle_timeout_minutes": DEFAULT_SESSION_IDLE_TIMEOUT_IN_MINUTES,
        "max_duration_minutes": DEFAULT_SESSION_MAX_DURATION_IN_MINUTES,
        "created_at": dt.datetime.now(),
        "last_accessed_at": dt.datetime.now(),
        "duration": dt.timedelta(seconds=100),
        "status": "closed" if close else "active",
    }


def test_open_viewer_true_spawns_viewer(client: NotteClient, session_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that open_viewer=True spawns the viewer."""
    _ = fake(monkeypatch, session_response_dict(session_id))
    session = client.Session(open_viewer=True, _client=client.sessions)
    with patch.object(session, "viewer") as mock_viewer:
        session.start()
        # Viewer should be called when open_viewer=True
        mock_viewer.assert_called_once()


def test_open_viewer_false_no_viewer(client: NotteClient, session_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that open_viewer=False does not spawn the viewer."""
    _ = fake(monkeypatch, session_response_dict(session_id))
    session = client.Session(open_viewer=False, _client=client.sessions)
    with patch.object(session, "viewer") as mock_viewer:
        session.start()
        # Viewer should not be called when open_viewer=False
        mock_viewer.assert_not_called()


def test_remote_session_omits_headless_on_wire(
    client: NotteClient, session_id: str, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake(monkeypatch, session_response_dict(session_id))
    session = client.Session(open_viewer=True, _client=client.sessions)
    with patch.object(session, "viewer"):
        session.start()

    # Verify the request was made
    assert api.calls

    # Get the call arguments - find the start request
    calls = [call for call in api.calls if call.method == "POST" and "start" in call.url]
    if calls:
        request_data = json.loads(calls[0].data)
        assert "headless" not in request_data
        assert "advanced_stealth" not in request_data


def test_remote_cdp_session_omits_viewport_on_wire(
    client: NotteClient, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake(monkeypatch, session_response_dict(session_id))
    session = client.Session(cdp_url="ws://localhost:9222")
    session.start()

    assert len(api.calls) == 1
    request_data = json.loads(api.calls[0].data)
    assert request_data["cdp_url"] == "ws://localhost:9222"
    assert "viewport_width" not in request_data
    assert "viewport_height" not in request_data


def _start_session(api: FakeSession, client: NotteClient, session_id: str) -> SessionResponse:
    """
    Mocks the HTTP response for starting a session and triggers session initiation.

    Configures the fake API to answer with a session dictionary constructed with the given
    session_id, then calls client.sessions.start() and returns its response.
    """
    api.payload = session_response_dict(session_id)
    api.status_code = 200
    return client.sessions.start()


def _stop_session(api: FakeSession, client: NotteClient, session_id: str) -> SessionResponse:
    api.payload = session_response_dict(session_id, close=True)
    api.status_code = 200
    return client.sessions.stop(session_id)


def _timeout(seconds: float) -> dict[str, float]:
    # requests applied one timeout to connecting and to each read; httpx also bounds writes and the pool.
    return {"connect": seconds, "read": seconds, "write": seconds, "pool": seconds}


@pytest.mark.order(1)
def test_start_session(
    client: NotteClient, session_id: str, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake(monkeypatch, None)
    session_data: SessionStartRequestDict = {"viewport_width": 1920, "viewport_height": 1080}
    response = _start_session(api, client=client, session_id=session_id)
    assert response.session_id == session_id
    assert response.error is None

    assert len(api.calls) == 1
    call = api.calls[0]
    assert (call.method, call.url) == ("POST", f"{client.sessions.server_url}/sessions/start")
    assert call.headers == headers
    assert call.data == SessionStartRequest.from_data(session_data).model_dump_json(exclude_none=True)
    assert call.params == {}
    assert call.files == {}
    assert call.timeout == _timeout(client.sessions.DEFAULT_REQUEST_TIMEOUT_SECONDS)


@pytest.mark.order(2)
def test_close_session(
    client: NotteClient, session_id: str, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake(monkeypatch, None)
    response = _stop_session(api, client=client, session_id=session_id)
    assert response.session_id == session_id
    assert response.status == "closed"
    headers_copy = headers.copy()
    headers_copy.pop("Content-Type")
    assert len(api.calls) == 1
    call = api.calls[0]
    assert (call.method, call.url) == ("DELETE", f"{client.sessions.server_url}/sessions/{session_id}/stop")
    assert call.headers == headers_copy
    assert call.params == {}
    assert call.data is None
    assert call.timeout == _timeout(client.sessions.DEFAULT_REQUEST_TIMEOUT_SECONDS)


def test_scrape(client: NotteClient, session_id: str, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = {
        "markdown": "test space",
        "session": session_response_dict(session_id),
    }
    api = fake(monkeypatch, mock_response)

    data = client.sessions.page.scrape(session_id)

    assert isinstance(data, str)
    assert data == "test space"
    assert len(api.calls) == 1
    assert api.calls[0].method == "POST"
    assert api.calls[0].headers == headers
    assert "model" not in json.loads(api.calls[0].data)


def test_scrape_sends_model(client: NotteClient, session_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(
        monkeypatch,
        {
            "markdown": "test space",
            "structured": {"success": True, "error": None, "data": {"title": "t"}},
            "session": session_response_dict(session_id),
        },
    )

    _ = client.sessions.page.scrape(session_id, instructions="extract", model="vertex_ai/gemini-3.5-flash")

    body = json.loads(api.calls[0].data)
    assert body["model"] == "vertex_ai/gemini-3.5-flash"
    assert body["instructions"] == "extract"


@pytest.mark.parametrize("start_session", [True, False])
def test_observe(
    client: NotteClient,
    headers: dict[str, str],
    start_session: bool,
    session_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = fake(monkeypatch, None)
    if start_session:
        _ = _start_session(api, client, session_id)
    mock_response = {
        "started_at": dt.datetime.now(),
        "ended_at": dt.datetime.now(),
        "metadata": {
            "title": "Test Page",
            "url": "https://example.com",
            "timestamp": dt.datetime.now(),
            "viewport": {
                "scroll_x": 0,
                "scroll_y": 0,
                "viewport_width": 1000,
                "viewport_height": 1000,
                "total_width": 1000,
                "total_height": 1000,
            },
            "tabs": [],
        },
        "space": {
            "description": "test space",
            "interaction_actions": [
                {"type": "click", "id": "L0", "description": "my_description_0", "category": "homepage"},
                {"type": "click", "id": "L1", "description": "my_description_1", "category": "homepage"},
            ],
            "browser_actions": [s.model_dump() for s in BrowserAction.list()],
            "category": "homepage",
        },
        # as the API sends it: base64 text
        "screenshot": Observation.empty().screenshot.model_dump(mode="json"),
        "progress": None,
    }
    api.payload = mock_response
    calls_before = len(api.calls)

    observation = client.sessions.page.observe(session_id=session_id)

    assert isinstance(observation, Observation)
    assert observation.metadata.url == "https://example.com"
    assert len(observation.space.interaction_actions) > 0
    assert len(observation.space.browser_actions) > 0
    assert observation.screenshot.raw == Observation.empty().screenshot.raw

    if not start_session:
        assert len(api.calls) == 1
    actual_call = api.calls[calls_before]
    assert actual_call.method == "POST"
    assert actual_call.headers == headers

    if start_session:
        _ = _stop_session(api, client=client, session_id=session_id)


@pytest.mark.parametrize("start_session", [True, False])
def test_step(
    client: NotteClient,
    headers: dict[str, str],
    start_session: bool,
    session_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Tests the client's step method with an optional session start.

    Simulates sending a step action with a defined payload and a mocked HTTP response.
    If start_session is True, a session is initiated before calling the step method and the
    client's session ID is verified; otherwise, it confirms that no session is maintained.
    The test asserts that the returned observation contains the expected metadata and that
    the HTTP request includes the appropriate authorization header and JSON payload.
    """
    api = fake(monkeypatch, None)
    if start_session:
        _ = _start_session(api, client, session_id)
    mock_response = {
        "started_at": dt.datetime.now(),
        "ended_at": dt.datetime.now(),
        "data": {
            "markdown": "test data",
        },
        "action": {"type": "fill", "id": "I1", "value": "#submit-button", "enter": False},
        "success": True,
        "message": "test message",
    }
    api.payload = mock_response
    calls_before = len(api.calls)

    step_data: ExecutionRequestDict = {
        "type": "fill",
        "id": "I1",
        "value": "#submit-button",
        "enter": False,
    }
    action = ExecutionRequest.get_action(step_data)
    obs = client.sessions.page.execute(session_id=session_id, action=action)

    assert isinstance(obs, ExecutionResult)
    assert obs.success
    assert obs.message == "test message"

    if not start_session:
        assert len(api.calls) == 1
    actual_call = api.calls[calls_before]
    assert actual_call.method == "POST"
    assert actual_call.headers == headers
    assert json.loads(actual_call.data)["id"] == "I1"
    assert json.loads(actual_call.data)["value"] == "#submit-button"

    if start_session:
        _ = _stop_session(api, client=client, session_id=session_id)


def test_format_observe_response(client: NotteClient, session_id: str) -> None:
    response_dict = {
        "status": 200,
        "started_at": dt.datetime.now(),
        "ended_at": dt.datetime.now(),
        "metadata": {
            "title": "Test Page",
            "url": "https://example.com",
            "timestamp": dt.datetime.now(),
            "viewport": {
                "scroll_x": 0,
                "scroll_y": 0,
                "viewport_width": 1000,
                "viewport_height": 1000,
                "total_width": 1000,
                "total_height": 1000,
            },
            "tabs": [],
        },
        "screenshot": {"raw": Observation.empty().screenshot.raw},
        "data": {"markdown": "my sample data"},
        "space": {
            "markdown": "test space",
            "description": "test space",
            "interaction_actions": [
                {"type": "click", "id": "L0", "description": "my_description_0", "category": "homepage"},
                {"type": "click", "id": "L1", "description": "my_description_1", "category": "homepage"},
            ],
            "browser_actions": [s.model_dump() for s in BrowserAction.list()],
            "category": "homepage",
        },
        "progress": None,
    }

    obs = ObserveResponse.model_validate(response_dict)
    assert obs.metadata.url == "https://example.com"
    assert obs.metadata.title == "Test Page"
    assert obs.screenshot.raw == Observation.empty().screenshot.raw

    assert obs.space is not None
    assert obs.space.description == "test space"
    assert obs.space.interaction_actions == [
        ClickAction(
            id="L0",
            description="my_description_0",
            category="homepage",
            param=None,
        ),
        ClickAction(
            id="L1",
            description="my_description_1",
            category="homepage",
            param=None,
        ),
    ]
    assert obs.space.category == SpaceCategory.HOMEPAGE


# ============================================================================
# Timeout Parameters Tests
# ============================================================================


def test_new_timeout_parameters_with_defaults() -> None:
    """Test new timeout parameters use correct defaults."""
    request = SessionStartRequest()
    assert request.max_duration_minutes == DEFAULT_SESSION_MAX_DURATION_IN_MINUTES
    assert request.idle_timeout_minutes == DEFAULT_SESSION_IDLE_TIMEOUT_IN_MINUTES


def test_solve_captchas_defaults_to_enabled_but_can_be_disabled() -> None:
    request = SessionStartRequest()
    assert request.solve_captchas is True
    assert SessionStartRequest(solve_captchas=False).solve_captchas is False


@pytest.mark.parametrize("options, expected", [({}, None), ({"block_ads": True}, True), ({"block_ads": False}, False)])
@pytest.mark.parametrize("high_level", [True, False])
def test_ad_blocking_is_serialized_for_remote_sessions(
    client: NotteClient,
    session_id: str,
    options: SessionStartRequestDict,
    expected: bool | None,
    high_level: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = fake(monkeypatch, session_response_dict(session_id))
    if high_level:
        session = client.Session(**options)
        session.start()
    else:
        _ = client.sessions.start(**options)
    assert len(api.calls) == 1
    payload = json.loads(api.calls[0].data)
    if expected is None:
        assert "block_ads" not in payload
    else:
        assert payload["block_ads"] is expected


def test_ad_blocking_option_is_remote_only() -> None:
    assert SessionStartRequest().block_ads is True
    assert "block_ads" not in LocalSessionStartRequest.model_fields


def test_proxies_default_to_enabled_but_can_be_disabled() -> None:
    request = SessionStartRequest()
    assert request.proxies is True
    assert SessionStartRequest(proxies=False).proxies is False
    assert LocalSessionStartRequest().proxies is False


def test_managed_auth_ids_are_serialized_without_local_validation() -> None:
    assert SessionStartRequest().auth_ids == []

    auth_ids = [
        "managed-auth-connection-primary",
        "managed-auth-connection-secondary",
    ]
    request = SessionStartRequest(auth_ids=auth_ids)

    assert request.auth_ids == auth_ids
    assert request.model_dump(mode="json")["auth_ids"] == auth_ids

    ten_auth_ids = [f"managed-auth-connection-{index}" for index in range(10)]
    assert SessionStartRequest(auth_ids=ten_auth_ids).auth_ids == ten_auth_ids

    # Duplicate/max-count validation now happens on the API request path.
    for invalid in [auth_ids * 2, [*ten_auth_ids, "managed-auth-connection-10"]]:
        assert SessionStartRequest.from_data({"auth_ids": invalid}).auth_ids == invalid


def test_managed_auth_connection_check(
    client: NotteClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_id = "55555555-5555-5555-5555-555555555555"
    api = fake(
        monkeypatch,
        {
            "connection_id": auth_id,
            "status": "authenticated",
            "message": "Authentication check completed",
        },
    )

    result = client.managed_auth.check_connection(auth_id)

    assert result.status == "authenticated"
    assert len(api.calls) == 1
    call = api.calls[0]
    assert (call.method, call.url) == (
        "POST",
        f"{client.managed_auth.server_url}/managed-auth/connections/{auth_id}/check",
    )
    assert call.headers == headers
    assert call.data == "{}"
    assert call.params == {}
    assert call.files == {}
    assert call.timeout == _timeout(client.managed_auth.DEFAULT_REQUEST_TIMEOUT_SECONDS)


def test_system_session_filter_is_session_specific_and_only_sent_explicitly() -> None:
    assert "include_system" not in SessionListRequest().model_dump(exclude_none=True)
    assert SessionListRequest(include_system=False).model_dump(exclude_none=True)["include_system"] is False
    assert "include_system" not in VaultListRequest().model_dump()


def test_new_timeout_parameters_explicit() -> None:
    """Test new explicit timeout parameters."""
    request = SessionStartRequest(max_duration_minutes=10, idle_timeout_minutes=5)
    assert request.max_duration_minutes == 10
    assert request.idle_timeout_minutes == 5


def test_timeout_minutes_backward_compatibility() -> None:
    """Test that old timeout_minutes parameter maps to idle_timeout_minutes."""
    import warnings

    with warnings.catch_warnings(record=True):
        request = SessionStartRequest.model_validate(dict(timeout_minutes=7))
    # Should map to idle_timeout_minutes
    assert request.idle_timeout_minutes == 7
    assert request.max_duration_minutes == DEFAULT_SESSION_MAX_DURATION_IN_MINUTES


def test_max_duration_validation() -> None:
    """Test max_duration_minutes validation (must be <= 24 * 60)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        _ = SessionStartRequest(max_duration_minutes=24 * 60 + 1)

    # Check that the error is about the max_duration_minutes field
    assert "max_duration_minutes" in str(exc_info.value)

    # Should work with values up to the 24h ceiling; per-tier enforcement
    # happens server-side, the SDK only guards the absolute upper bound.
    request = SessionStartRequest(max_duration_minutes=DEFAULT_SESSION_MAX_DURATION_IN_MINUTES)
    assert request.max_duration_minutes == DEFAULT_SESSION_MAX_DURATION_IN_MINUTES
    request = SessionStartRequest(max_duration_minutes=24 * 60)
    assert request.max_duration_minutes == 24 * 60


@pytest.mark.parametrize("value", [0, -5])
def test_idle_timeout_validation(monkeypatch, value) -> None:
    from tests.sdk.test_types import assert_start_api_validation

    assert_start_api_validation(monkeypatch, {"idle_timeout_minutes": value})


def test_session_start_with_new_timeout_params(
    client: NotteClient, session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test session start with new timeout parameters."""
    max_duration_minutes = 10
    idle_timeout_minutes = 5
    api = fake(
        monkeypatch,
        {
            "session_id": session_id,
            "max_duration_minutes": max_duration_minutes,
            "idle_timeout_minutes": idle_timeout_minutes,
            "status": "active",
            "created_at": dt.datetime.now().isoformat(),
            "last_accessed_at": dt.datetime.now().isoformat(),
        },
    )

    session = client.Session(
        max_duration_minutes=max_duration_minutes,
        idle_timeout_minutes=idle_timeout_minutes,
        _client=client.sessions,
    )
    session.start()

    # Verify the request was made with correct params
    assert api.calls
    request_data = json.loads(api.calls[-1].data)
    assert request_data["max_duration_minutes"] == max_duration_minutes
    assert request_data["idle_timeout_minutes"] == idle_timeout_minutes
