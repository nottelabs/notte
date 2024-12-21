import os
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

from notte.browser.observation import Observation
from notte.sdk.client import NotteClient
from notte.sdk.types import (
    ObserveRequestDict,
    ObserveResponseDict,
    SessionRequestDict,
    SessionResponseDict,
    StepRequestDict,
)

_ = load_dotenv()


@pytest.fixture
def client() -> NotteClient:
    return NotteClient()


@pytest.fixture
def mock_response() -> MagicMock:
    return MagicMock()


def test_client_initialization_with_env_vars() -> None:
    client = NotteClient()
    assert client.token == os.getenv("NOTTE_API_KEY")
    assert client.server_url == NotteClient.DEFAULT_SERVER_URL
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


@patch("requests.post")
def test_create_session(mock_post: MagicMock, client: NotteClient) -> None:
    mock_response: SessionResponseDict = {
        "session_id": "test-session-123",
    }
    mock_post.return_value.json.return_value = mock_response

    session_data: SessionRequestDict = {
        "session_id": None,
        "keep_alive": False,
        "session_timeout": 10,
        "screenshot": True,
    }
    response = client.create_session(**session_data)

    assert client.session_id == "test-session-123"
    mock_post.assert_called_once_with(
        f"{client.server_url}/session/create",
        headers={"Authorization": f"Bearer {os.getenv('NOTTE_API_KEY')}"},
        json=session_data,
    )


@patch("requests.post")
def test_close_session(mock_post: MagicMock, client: NotteClient) -> None:
    client.session_id = "test-session-123"

    mock_response: SessionResponseDict = {"session_id": "test-session-123"}
    mock_post.return_value.json.return_value = mock_response

    session_data: SessionRequestDict = {
        "session_id": "test-session-123",
        "keep_alive": False,
        "session_timeout": 10,
        "screenshot": True,
    }
    response = client.close_session(**session_data)

    assert client.session_id is None
    mock_post.assert_called_once_with(
        f"{client.server_url}/session/close",
        headers={"Authorization": f"Bearer {os.getenv('NOTTE_API_KEY')}"},
        json=session_data,
    )


@patch("requests.post")
def test_scrape(mock_post: MagicMock, client: NotteClient) -> None:
    mock_response: ObserveResponseDict = {
        "url": "https://example.com",
        "actions": None,
        "data": "",
        "screenshot": None,
        "session_id": "test-session-123",
    }
    mock_post.return_value.json.return_value = mock_response

    observe_data: ObserveRequestDict = {"url": "https://example.com", "session_id": "test-session-123"}
    observation = client.scrape(**observe_data)

    assert isinstance(observation, Observation)
    mock_post.assert_called_once()
    actual_call = mock_post.call_args
    assert actual_call.kwargs["headers"] == {"Authorization": f"Bearer {os.getenv('NOTTE_API_KEY')}"}
    assert actual_call.kwargs["json"]["url"] == "https://example.com"
    assert actual_call.kwargs["json"]["session_id"] == "test-session-123"


@patch("requests.post")
def test_scrape_without_url_or_session_id(mock_post: MagicMock, client: NotteClient) -> None:
    observe_data: ObserveRequestDict = {
        "url": None,
        "session_id": None,
        "keep_alive": False,
        "session_timeout": 10,
        "screenshot": True,
    }
    with pytest.raises(ValueError, match="Either url or session_id needs to be provided"):
        client.scrape(**observe_data)


@patch("requests.post")
def test_observe(mock_post: MagicMock, client: NotteClient) -> None:
    mock_response: ObserveResponseDict = {"url": "https://example.com", "actions": None, "data": "", "screenshot": None}
    mock_post.return_value.json.return_value = mock_response

    observation = client.observe(url="https://example.com")

    assert isinstance(observation, Observation)
    mock_post.assert_called_once_with(
        f"{client.server_url}/env/observe",
        headers={"Authorization": f"Bearer {os.getenv('NOTTE_API_KEY')}"},
        json={"url": "https://example.com"},
    )


@patch("requests.post")
def test_step(mock_post: MagicMock, client: NotteClient) -> None:
    mock_response: ObserveResponseDict = {"url": "https://example.com", "actions": None, "data": "", "screenshot": None}
    mock_post.return_value.json.return_value = mock_response

    step_data: StepRequestDict = {
        "action_id": "click",
        "value": "#submit-button",
        "enter": False,
        "session_id": "test-session-123",
    }
    observation = client.step(**step_data)

    assert isinstance(observation, Observation)
    mock_post.assert_called_once_with(
        f"{client.server_url}/env/step",
        headers={"Authorization": f"Bearer {os.getenv('NOTTE_API_KEY')}"},
        json=step_data,
    )
