import datetime as dt
import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from notte_core import __version__ as notte_core_version
from notte_core.actions import BrowserAction, ClickAction
from notte_core.browser.observation import ExecutionResult, Observation
from notte_core.space import SpaceCategory
from notte_sdk.client import NotteClient
from notte_sdk.errors import AuthenticationError
from notte_sdk.types import (
    DEFAULT_SESSION_IDLE_TIMEOUT_IN_MINUTES,
    DEFAULT_SESSION_MAX_DURATION_IN_MINUTES,
    ExecutionRequest,
    ExecutionRequestDict,
    ObserveResponse,
    SessionResponse,
    SessionStartRequest,
    SessionStartRequestDict,
)


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
        "x-notte-request-origin": "sdk",
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
    with patch.dict(os.environ, clear=True):
        with pytest.raises(AuthenticationError):
            _ = NotteClient()


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


def test_open_viewer_true_spawns_viewer(client: NotteClient, session_id: str) -> None:
    """Test that open_viewer=True spawns the viewer."""
    with patch("requests.post") as mock_post:
        mock_response = session_response_dict(session_id)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response

        session = client.Session(open_viewer=True, _client=client.sessions)
        with patch.object(session, "viewer") as mock_viewer:
            session.start()
            # Viewer should be called when open_viewer=True
            mock_viewer.assert_called_once()


def test_open_viewer_false_no_viewer(client: NotteClient, session_id: str) -> None:
    """Test that open_viewer=False does not spawn the viewer."""
    with patch("requests.post") as mock_post:
        mock_response = session_response_dict(session_id)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response

        session = client.Session(open_viewer=False, _client=client.sessions)
        with patch.object(session, "viewer") as mock_viewer:
            session.start()
            # Viewer should not be called when open_viewer=False
            mock_viewer.assert_not_called()


def test_session_always_headless_true_on_wire(client: NotteClient, session_id: str, headers: dict[str, str]) -> None:
    """Test that session start requests always include headless=True."""
    with patch("requests.post") as mock_post, patch.object(client.sessions, "viewer"):
        mock_response = session_response_dict(session_id)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response

        session = client.Session(open_viewer=True, _client=client.sessions)
        session.start()

        # Verify the request was made
        assert mock_post.called

        # Get the call arguments - find the start request
        calls = [call for call in mock_post.call_args_list if "start" in str(call)]
        if calls:
            call_args = calls[0]
            request_data = json.loads(call_args.kwargs["data"])
            # Verify headless is always True in the wire request
            assert request_data["headless"] is True
        else:
            # Fallback: check the request attribute directly
            assert session.request.headless is True


def _start_session(mock_post: MagicMock, client: NotteClient, session_id: str) -> SessionResponse:
    """
    Mocks the HTTP response for starting a session and triggers session initiation.

    Configures the provided mock_post to simulate a successful HTTP response using a session
    dictionary constructed with the given session_id, then calls client.sessions.start() and
    returns its response.
    """
    mock_response = session_response_dict(session_id)
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response
    return client.sessions.start()


def _stop_session(mock_delete: MagicMock, client: NotteClient, session_id: str) -> SessionResponse:
    mock_response = session_response_dict(session_id, close=True)
    mock_delete.return_value.status_code = 200
    mock_delete.return_value.json.return_value = mock_response
    return client.sessions.stop(session_id)


@patch("requests.post")
@pytest.mark.order(1)
def test_start_session(mock_post: MagicMock, client: NotteClient, session_id: str, headers: dict[str, str]) -> None:
    session_data: SessionStartRequestDict = {
        "headless": True,
        "solve_captchas": False,
        "idle_timeout_minutes": DEFAULT_SESSION_IDLE_TIMEOUT_IN_MINUTES,
        "max_duration_minutes": DEFAULT_SESSION_MAX_DURATION_IN_MINUTES,
        "proxies": False,
        "browser_type": "chromium",
        "viewport_width": 1920,
        "viewport_height": 1080,
        "use_file_storage": False,
    }
    response = _start_session(mock_post=mock_post, client=client, session_id=session_id)
    assert response.session_id == session_id
    assert response.error is None

    mock_post.assert_called_once_with(
        url=f"{client.sessions.server_url}/sessions/start",
        headers=headers,
        data=SessionStartRequest.model_validate(session_data).model_dump_json(exclude_none=True),
        params=None,
        timeout=client.sessions.DEFAULT_REQUEST_TIMEOUT_SECONDS,
        files=None,
        json=None,
    )


@patch("requests.delete")
@pytest.mark.order(2)
def test_close_session(mock_delete: MagicMock, client: NotteClient, session_id: str, headers: dict[str, str]) -> None:
    response = _stop_session(mock_delete=mock_delete, client=client, session_id=session_id)
    assert response.session_id == session_id
    assert response.status == "closed"
    headers_copy = headers.copy()
    headers_copy.pop("Content-Type")
    mock_delete.assert_called_once_with(
        url=f"{client.sessions.server_url}/sessions/{session_id}/stop",
        headers=headers_copy,
        params=None,
        timeout=client.sessions.DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )


@patch("requests.post")
def test_scrape(mock_post: MagicMock, client: NotteClient, session_id: str, headers: dict[str, str]) -> None:
    mock_response = {
        "markdown": "test space",
        "session": session_response_dict(session_id),
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    data = client.sessions.page.scrape(session_id)

    assert isinstance(data, str)
    assert data == "test space"
    mock_post.assert_called_once()
    actual_call = mock_post.call_args
    assert actual_call.kwargs["headers"] == headers


@pytest.mark.parametrize("start_session", [True, False])
@patch("requests.delete")
@patch("requests.post")
def test_observe(
    mock_post: MagicMock,
    mock_delete: MagicMock,
    client: NotteClient,
    headers: dict[str, str],
    start_session: bool,
    session_id: str,
) -> None:
    if start_session:
        _ = _start_session(mock_post, client, session_id)
    mock_response = {
        "session": session_response_dict(session_id),
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
        "screenshot": {"raw": Observation.empty().screenshot.raw},
        "progress": None,
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    observation = client.sessions.page.observe(session_id=session_id)

    assert isinstance(observation, Observation)
    assert observation.metadata.url == "https://example.com"
    assert len(observation.space.interaction_actions) > 0
    assert len(observation.space.browser_actions) > 0
    assert observation.screenshot.raw == Observation.empty().screenshot.raw

    if not start_session:
        mock_post.assert_called_once()
    actual_call = mock_post.call_args
    assert actual_call.kwargs["headers"] == headers

    if start_session:
        _ = _stop_session(mock_delete=mock_delete, client=client, session_id=session_id)


@pytest.mark.parametrize("start_session", [True, False])
@patch("requests.delete")
@patch("requests.post")
def test_step(
    mock_post: MagicMock,
    mock_delete: MagicMock,
    client: NotteClient,
    headers: dict[str, str],
    start_session: bool,
    session_id: str,
) -> None:
    """
    Tests the client's step method with an optional session start.

    Simulates sending a step action with a defined payload and a mocked HTTP response.
    If start_session is True, a session is initiated before calling the step method and the
    client's session ID is verified; otherwise, it confirms that no session is maintained.
    The test asserts that the returned observation contains the expected metadata and that
    the HTTP request includes the appropriate authorization header and JSON payload.
    """
    if start_session:
        _ = _start_session(mock_post, client, session_id)
    mock_response = {
        "session": session_response_dict(session_id),
        "data": {
            "markdown": "test data",
        },
        "action": {"type": "fill", "id": "I1", "value": "#submit-button", "enter": False},
        "success": True,
        "message": "test message",
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

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
        mock_post.assert_called_once()
    actual_call = mock_post.call_args
    assert actual_call.kwargs["headers"] == headers
    assert json.loads(actual_call.kwargs["data"])["id"] == "I1"
    assert json.loads(actual_call.kwargs["data"])["value"] == "#submit-button"

    if start_session:
        _ = _stop_session(mock_delete=mock_delete, client=client, session_id=session_id)


def test_format_observe_response(client: NotteClient, session_id: str) -> None:
    response_dict = {
        "status": 200,
        "session": session_response_dict(session_id),
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
    """Test max_duration_minutes validation (must be <= 60)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        test_max_duration = DEFAULT_SESSION_MAX_DURATION_IN_MINUTES + 1
        _ = SessionStartRequest(max_duration_minutes=test_max_duration)

    # Check that the error is about the max_duration_minutes field
    assert "max_duration_minutes" in str(exc_info.value)

    # Should work with valid value
    request = SessionStartRequest(max_duration_minutes=DEFAULT_SESSION_MAX_DURATION_IN_MINUTES)
    assert request.max_duration_minutes == DEFAULT_SESSION_MAX_DURATION_IN_MINUTES


def test_idle_timeout_validation() -> None:
    """Test idle_timeout_minutes validation (must be > 0)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _ = SessionStartRequest(idle_timeout_minutes=0)

    with pytest.raises(ValidationError):
        _ = SessionStartRequest(idle_timeout_minutes=-5)


def test_session_start_with_new_timeout_params(client: NotteClient, session_id: str) -> None:
    """Test session start with new timeout parameters."""
    max_duration_minutes = 10
    idle_timeout_minutes = 5
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "session_id": session_id,
            "max_duration_minutes": max_duration_minutes,
            "idle_timeout_minutes": idle_timeout_minutes,
            "status": "active",
            "created_at": dt.datetime.now().isoformat(),
            "last_accessed_at": dt.datetime.now().isoformat(),
        }

        session = client.Session(
            max_duration_minutes=max_duration_minutes,
            idle_timeout_minutes=idle_timeout_minutes,
            _client=client.sessions,
        )
        session.start()

        # Verify the request was made with correct params
        assert mock_post.called
        call_args = mock_post.call_args
        request_data = json.loads(call_args[1]["data"])
        assert request_data["max_duration_minutes"] == max_duration_minutes
        assert request_data["idle_timeout_minutes"] == idle_timeout_minutes
