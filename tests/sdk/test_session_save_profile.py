from unittest.mock import MagicMock, patch

import pytest
from notte_sdk.endpoints.base import BaseClient
from notte_sdk.endpoints.sessions import RemoteSession, SessionsClient
from notte_sdk.types import ProfileResponse, SessionProfileSaveRequest
from pydantic import ValidationError

PROFILE = {
    "profile_id": "notte-profile-0123456789abcdef",
    "name": "github",
    "created_at": "2026-10-13T00:00:00Z",
    "updated_at": "2026-10-13T00:00:00Z",
    "persisted_domains": ["github.com"],
}


def _client() -> SessionsClient:
    client = object.__new__(SessionsClient)
    return client


def test_save_profile_endpoint_targets_session() -> None:
    endpoint = SessionsClient._session_save_profile_endpoint(session_id="session-id")

    assert endpoint.path == "session-id/profile/save"
    assert endpoint.method == "POST"
    assert endpoint.response is ProfileResponse


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"profile_id": "notte-profile-0123456789abcdef"}, {"profile_id": "notte-profile-0123456789abcdef"}),
        ({"name": "github"}, {"name": "github"}),
        ({}, {}),
    ],
)
def test_client_save_profile_sends_the_target(data: dict[str, str], expected: dict[str, str]) -> None:
    client = _client()
    with patch.object(BaseClient, "_request", return_value=PROFILE) as request:
        profile = client.save_profile("session-id", **data)  # pyright: ignore[reportArgumentType]

    endpoint = request.call_args.args[0]
    assert endpoint.path == "session-id/profile/save"
    assert endpoint.request.model_dump(exclude_none=True) == expected
    assert profile.profile_id == PROFILE["profile_id"]
    assert profile.persisted_domains == ["github.com"]


@pytest.mark.parametrize(
    "data",
    [
        {"profile_id": "notte-profile-0123456789abcdef", "name": "github"},
        {"profile_id": ""},
        {"name": ""},
        {"profile_id": "  "},
        {"name": " "},
    ],
)
def test_save_profile_request_rejects_invalid_targets(data: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        _ = SessionProfileSaveRequest.model_validate(data)


def test_remote_session_save_profile_forwards_only_given_target() -> None:
    session = object.__new__(RemoteSession)
    session.client = MagicMock()
    session.client.save_profile.return_value = ProfileResponse.model_validate(PROFILE)
    with patch.object(RemoteSession, "session_id", new="session-id"):
        profile = session.save_profile(name="github")

    session.client.save_profile.assert_called_once_with(session_id="session-id", name="github")
    assert profile.name == "github"
