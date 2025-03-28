import datetime as dt
import os
from unittest.mock import MagicMock, patch

import pytest

from notte.actions.base import Action, BrowserAction
from notte.browser.observation import Observation
from notte.controller.space import SpaceCategory
from notte.sdk.client import NotteClient
from notte.sdk.types import (
    DEFAULT_MAX_NB_STEPS,
    DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES,
    ObserveRequestDict,
    ObserveResponse,
    SessionResponse,
    SessionResponseDict,
    SessionStartRequestDict,
    StepRequestDict,
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
def mock_response() -> MagicMock:
    return MagicMock()


def test_client_initialization_with_env_vars() -> None:
    client = NotteClient(api_key="test-api-key")
    assert client.sessions.token == "test-api-key"


def test_client_initialization_with_params() -> None:
    client = NotteClient(api_key="custom-api-key")
    assert client.sessions.token == "custom-api-key"
    assert client.sessions.session_id is None


def test_client_initialization_without_api_key() -> None:
    with patch.dict(os.environ, clear=True):
        with pytest.raises(ValueError, match="NOTTE_API_KEY needs to be provide"):
            _ = NotteClient()


@pytest.fixture
def session_id() -> str:
    return "test-session-123"


def session_response_dict(session_id: str, close: bool = False) -> SessionResponseDict:
    return {
        "session_id": session_id,
        "timeout_minutes": DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES,
        "created_at": dt.datetime.now(),
        "last_accessed_at": dt.datetime.now(),
        "duration": dt.timedelta(seconds=100),
        "status": "closed" if close else "active",
    }


def _start_session(mock_post: MagicMock, client: NotteClient, session_id: str) -> SessionResponse:
    """
    Mocks the HTTP response for starting a session and triggers session initiation.

    Configures the provided mock_post to simulate a successful HTTP response using a session
    dictionary constructed with the given session_id, then calls client.sessions.start() and
    returns its response.
    """
    mock_response: SessionResponseDict = session_response_dict(session_id)
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response
    return client.sessions.start()


@patch("requests.post")
def test_start_session(mock_post: MagicMock, client: NotteClient, api_key: str, session_id: str) -> None:
    session_data: SessionStartRequestDict = {
        "timeout_minutes": DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES,
        "screenshot": None,
        "max_steps": DEFAULT_MAX_NB_STEPS,
        "proxies": None,
        "keep_alive": False,
        "session_id": None,
    }
    response = _start_session(mock_post=mock_post, client=client, session_id=session_id)
    assert response.session_id == session_id
    assert response.error is None

    assert client.sessions.session_id == session_id
    mock_post.assert_called_once_with(
        url=f"{client.sessions.server_url}/sessions/start",
        headers={"Authorization": f"Bearer {api_key}"},
        json=session_data,
        params=None,
        timeout=client.sessions.DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )


@patch("requests.delete")
def test_close_session(mock_delete: MagicMock, client: NotteClient, api_key: str, session_id: str) -> None:
    mock_response: SessionResponseDict = session_response_dict(session_id, close=True)
    mock_delete.return_value.status_code = 200
    mock_delete.return_value.json.return_value = mock_response

    response = client.sessions.close(session_id)

    assert response.session_id == session_id
    assert response.status == "closed"
    mock_delete.assert_called_once_with(
        url=f"{client.sessions.server_url}/sessions/{session_id}/close",
        headers={"Authorization": f"Bearer {api_key}"},
        params=None,
        timeout=client.sessions.DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )


@patch("requests.post")
def test_scrape(mock_post: MagicMock, client: NotteClient, api_key: str, session_id: str) -> None:
    mock_response = {
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
        "space": None,
        "data": None,
        "screenshot": None,
        "session": session_response_dict(session_id),
        "progress": {
            "current_step": 1,
            "max_steps": 10,
        },
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    observe_data: ObserveRequestDict = {
        "url": "https://example.com",
        "session_id": session_id,
    }
    observation = client.env.scrape(**observe_data)

    assert isinstance(observation, Observation)
    mock_post.assert_called_once()
    actual_call = mock_post.call_args
    assert actual_call.kwargs["headers"] == {"Authorization": f"Bearer {api_key}"}
    assert actual_call.kwargs["json"]["url"] == "https://example.com"
    assert actual_call.kwargs["json"]["session_id"] == session_id


@patch("requests.post")
def test_scrape_without_url_or_session_id(mock_post: MagicMock, client: NotteClient) -> None:
    """
    Test scraping without a URL or session ID.

    Verifies that when both 'url' and 'session_id' are None, calling the scrape
    operation raises a ValueError with an appropriate error message.
    """
    observe_data: ObserveRequestDict = {
        "url": None,
        "session_id": None,
        "keep_alive": False,
        "timeout_minutes": DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES,
        "screenshot": True,
    }
    with pytest.raises(ValueError, match="Either url or session_id needs to be provided"):
        client.env.scrape(**observe_data)


@pytest.mark.parametrize("start_session", [True, False])
@patch("requests.post")
def test_observe(
    mock_post: MagicMock,
    client: NotteClient,
    api_key: str,
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
        "space": None,
        "data": None,
        "screenshot": None,
        "progress": {
            "current_step": 1,
            "max_steps": 10,
        },
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    observation = client.env.observe(session_id=session_id, url="https://example.com")

    assert isinstance(observation, Observation)
    if start_session:
        assert client.sessions.session_id == session_id
    assert observation.metadata.url == "https://example.com"
    assert not observation.has_space()
    assert not observation.has_data()
    assert observation.screenshot is None
    if not start_session:
        mock_post.assert_called_once()
    actual_call = mock_post.call_args
    assert actual_call.kwargs["headers"] == {"Authorization": f"Bearer {api_key}"}
    assert actual_call.kwargs["json"]["url"] == "https://example.com"
    if start_session:
        assert actual_call.kwargs["json"]["session_id"] == session_id
    else:
        # disable this test for now as we need to redesign keep_alive
        # assert actual_call.kwargs["json"]["session_id"] is None
        pass


@pytest.mark.parametrize("start_session", [True, False])
@patch("requests.post")
def test_step(
    mock_post: MagicMock,
    client: NotteClient,
    api_key: str,
    start_session: bool,
    session_id: str,
) -> None:
    """
    Tests the client's step method with an optional session start.

    Simulates sending a step action with a defined payload and a mocked HTTP response.
    If start_session is True, a session is initiated before calling the step method and the
    client’s session ID is verified; otherwise, it confirms that no session is maintained.
    The test asserts that the returned observation contains the expected metadata and that
    the HTTP request includes the appropriate authorization header and JSON payload.
    """
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
        "space": None,
        "data": None,
        "screenshot": None,
        "progress": {
            "current_step": 1,
            "max_steps": 10,
        },
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    step_data: StepRequestDict = {
        "action_id": "B1",
        "value": "#submit-button",
        "enter": False,
        "session_id": session_id,
    }
    observation = client.env.step(**step_data)

    assert isinstance(observation, Observation)
    if start_session:
        assert client.sessions.session_id == session_id
    else:
        assert client.sessions.session_id is None
    assert observation.metadata.url == "https://example.com"
    assert not observation.has_space()
    assert not observation.has_data()
    assert observation.screenshot is None

    if not start_session:
        mock_post.assert_called_once()
    actual_call = mock_post.call_args
    assert actual_call.kwargs["headers"] == {"Authorization": f"Bearer {api_key}"}
    assert actual_call.kwargs["json"]["action_id"] == "B1"
    assert actual_call.kwargs["json"]["value"] == "#submit-button"
    assert not actual_call.kwargs["json"]["enter"]
    assert actual_call.kwargs["json"]["session_id"] == session_id


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
        "screenshot": b"fake_screenshot",
        "data": {"markdown": "my sample data"},
        "space": {
            "markdown": "test space",
            "description": "test space",
            "actions": [
                {"id": "L0", "description": "my_description_0", "category": "homepage"},
                {"id": "L1", "description": "my_description_1", "category": "homepage"},
            ],
            "browser_actions": [s.model_dump() for s in BrowserAction.list()],
            "category": "homepage",
        },
        "progress": {
            "current_step": 1,
            "max_steps": 10,
        },
    }

    obs = client.env._format_observe_response(ObserveResponse.model_validate(response_dict))
    assert obs.metadata.url == "https://example.com"
    assert obs.metadata.title == "Test Page"
    assert obs.screenshot == b"fake_screenshot"
    assert obs.data is not None
    assert obs.data.markdown == "my sample data"
    assert obs.space is not None
    assert obs.space.description == "test space"
    assert obs.space.actions() == [
        Action(
            id="L0",
            description="my_description_0",
            category="homepage",
            params=[],
        ),
        Action(
            id="L1",
            description="my_description_1",
            category="homepage",
            params=[],
        ),
    ]
    assert obs.space.category == SpaceCategory.HOMEPAGE
