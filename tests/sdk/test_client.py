import datetime as dt
import os
from unittest.mock import MagicMock, patch

import pytest

from notte.actions.base import Action
from notte.actions.space import SpaceCategory
from notte.browser.observation import Observation
from notte.sdk.client import NotteClient
from notte.sdk.types import (
    DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES,
    ObserveRequestDict,
    SessionRequestDict,
    SessionResponse,
    SessionResponseDict,
    StepRequestDict,
)


@pytest.fixture
def api_key() -> str:
    return "test-api-key"


@pytest.fixture
def server_url() -> str:
    return "http://my-server.com"


@pytest.fixture
def client(api_key: str, server_url: str) -> NotteClient:
    return NotteClient(
        server_url=server_url,
        api_key=api_key,
    )


@pytest.fixture
def mock_response() -> MagicMock:
    return MagicMock()


def test_client_initialization_with_env_vars() -> None:
    client = NotteClient(server_url="http://my-server.com", api_key="test-api-key")
    assert client.token == "test-api-key"
    assert client.server_url == "http://my-server.com"
    assert client.session_id is None


def test_client_initialization_with_params() -> None:
    client = NotteClient(api_key="custom-api-key", server_url="http://custom-url.com")
    assert client.token == "custom-api-key"
    assert client.server_url == "http://custom-url.com"
    assert client.session_id is None


def test_client_initialization_without_api_key() -> None:
    with patch.dict(os.environ, clear=True):
        with pytest.raises(ValueError, match="NOTTE_API_KEY needs to be provide"):
            _ = NotteClient()


@pytest.fixture
def session_id() -> str:
    return "test-session-123"


def _start_session(mock_post: MagicMock, client: NotteClient, session_id: str) -> SessionResponse:
    mock_response: SessionResponseDict = {
        "session_id": session_id,
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response
    return client.start()


@patch("requests.post")
def test_start_session(mock_post: MagicMock, client: NotteClient, api_key: str, session_id: str) -> None:
    session_data: SessionRequestDict = {
        "session_id": None,
        "keep_alive": True,
        "session_timeout": DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES,
        "screenshot": None,
    }
    response = _start_session(mock_post=mock_post, client=client, session_id=session_id)
    assert response.session_id == session_id
    assert response.error is None

    assert client.session_id == session_id
    mock_post.assert_called_once_with(
        f"{client.server_url}/session/start",
        headers={"Authorization": f"Bearer {api_key}"},
        json=session_data,
    )


@patch("requests.post")
def test_close_session(mock_post: MagicMock, client: NotteClient, api_key: str) -> None:
    client.session_id = "test-session-123"

    mock_response: SessionResponseDict = {"session_id": "test-session-123"}
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    session_data: SessionRequestDict = {
        "session_id": "test-session-123",
        "keep_alive": False,
        "session_timeout": DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES,
        "screenshot": None,
    }
    response = client.close(**session_data)

    assert client.session_id is None
    assert response.session_id == "test-session-123"
    mock_post.assert_called_once_with(
        f"{client.server_url}/session/close",
        headers={"Authorization": f"Bearer {api_key}"},
        json=session_data,
    )


@patch("requests.post")
def test_scrape(mock_post: MagicMock, client: NotteClient, api_key: str) -> None:
    mock_response = {
        "title": "Test Page",
        "url": "https://example.com",
        "timestamp": dt.datetime.now(),
        "space": None,
        "data": None,
        "screenshot": None,
        "session_id": "test-session-123",
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    observe_data: ObserveRequestDict = {"url": "https://example.com", "session_id": "test-session-123"}
    observation = client.scrape(**observe_data)

    assert isinstance(observation, Observation)
    mock_post.assert_called_once()
    actual_call = mock_post.call_args
    assert actual_call.kwargs["headers"] == {"Authorization": f"Bearer {api_key}"}
    assert actual_call.kwargs["json"]["url"] == "https://example.com"
    assert actual_call.kwargs["json"]["session_id"] == "test-session-123"


@patch("requests.post")
def test_scrape_without_url_or_session_id(mock_post: MagicMock, client: NotteClient, api_key: str) -> None:
    observe_data: ObserveRequestDict = {
        "title": "Test Page",
        "url": None,
        "session_id": None,
        "keep_alive": False,
        "session_timeout": DEFAULT_OPERATION_SESSION_TIMEOUT_IN_MINUTES,
        "screenshot": True,
    }
    with pytest.raises(ValueError, match="Either url or session_id needs to be provided"):
        client.scrape(**observe_data)


@pytest.mark.parametrize("start_session", [True, False])
@patch("requests.post")
def test_observe(mock_post: MagicMock, client: NotteClient, api_key: str, start_session: bool, session_id: str) -> None:
    if start_session:
        _ = _start_session(mock_post, client, session_id)
    mock_response = {
        "session_id": session_id,
        "title": "Test Page",
        "url": "https://example.com",
        "timestamp": dt.datetime.now(),
        "space": None,
        "data": None,
        "screenshot": None,
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    observation = client.observe(url="https://example.com")

    assert isinstance(observation, Observation)
    if start_session:
        assert client.session_id == session_id
    assert observation.url == "https://example.com"
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
        assert actual_call.kwargs["json"]["session_id"] is None


@pytest.mark.parametrize("start_session", [True, False])
@patch("requests.post")
def test_step(mock_post: MagicMock, client: NotteClient, api_key: str, start_session: bool, session_id: str) -> None:
    if start_session:
        _ = _start_session(mock_post, client, session_id)
    mock_response = {
        "session_id": session_id,
        "url": "https://example.com",
        "title": "Test Page",
        "timestamp": dt.datetime.now(),
        "space": None,
        "data": None,
        "screenshot": None,
    }
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = mock_response

    step_data: StepRequestDict = {
        "action_id": "B1",
        "value": "#submit-button",
        "enter": False,
        "session_id": session_id,
    }
    observation = client.step(**step_data)

    assert isinstance(observation, Observation)
    if start_session:
        assert client.session_id == session_id
    else:
        assert client.session_id is None
    assert observation.url == "https://example.com"
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


def test_format_observe_response(client: NotteClient) -> None:
    response_dict = {
        "status": 200,
        "session_id": "test-session-123",
        "url": "https://example.com",
        "title": "Test Page",
        "timestamp": dt.datetime.now(),
        "screenshot": b"fake_screenshot",
        "data": {"markdown": "my sample data"},
        "space": {
            "description": "test space",
            "actions": [
                {"id": "L0", "description": "my_description_0", "category": "homepage"},
                {"id": "L1", "description": "my_description_1", "category": "homepage"},
            ],
            "category": "homepage",
        },
    }
    observation = client._format_observe_response(response_dict)
    assert observation.url == "https://example.com"
    assert observation.title == "Test Page"
    assert observation.screenshot == b"fake_screenshot"
    assert observation.data is not None
    assert observation.data.markdown == "my sample data"
    assert observation.space.description == "test space"
    assert observation.space.actions() == [
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
    assert observation.space.category == SpaceCategory.HOMEPAGE
