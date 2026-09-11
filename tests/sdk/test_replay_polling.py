from unittest.mock import Mock, patch

import pytest
from notte_sdk import NotteClient
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import ReplayResponse, SessionResponse

from tests.sdk.test_client import session_response_dict


def active_replay_error() -> NotteAPIError:
    response = Mock(status_code=404)
    response.json.return_value = {"message": "Session is still active — close it first"}
    return NotteAPIError("sessions/test-session/replay", response)


def test_replay_waits_for_persistence_after_successful_stop():
    client = NotteClient(api_key="test-key")
    session = RemoteSession(_client=client.sessions)
    session.response = SessionResponse.model_validate(session_response_dict("test-session", close=True))
    replay = ReplayResponse(mp4_url="https://example.com/replay.mp4")

    with (
        patch.object(client.sessions, "request", side_effect=[active_replay_error(), replay]) as request,
        patch("notte_sdk.endpoints.sessions.time.sleep") as sleep,
    ):
        assert session.replay() == replay

    assert request.call_count == 2
    sleep.assert_called_once_with(5.0)


def test_active_session_replay_still_fails_without_waiting():
    client = NotteClient(api_key="test-key")
    with (
        patch.object(client.sessions, "request", side_effect=active_replay_error()),
        patch("notte_sdk.endpoints.sessions.time.sleep") as sleep,
        pytest.raises(ValueError, match="still active"),
    ):
        client.sessions.replay("test-session")
    sleep.assert_not_called()


def test_closed_session_replay_polling_has_a_deadline():
    client = NotteClient(api_key="test-key")
    with (
        patch.object(client.sessions, "request", side_effect=active_replay_error()),
        pytest.raises(TimeoutError, match="not ready"),
    ):
        client.sessions.replay("test-session", timeout=0, _session_closed=True)
