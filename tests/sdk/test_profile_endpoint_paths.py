import datetime as dt
from unittest.mock import patch

from notte_sdk import NotteClient
from notte_sdk.endpoints.profiles import ProfilesClient
from notte_sdk.types import ProfileDuplicateRequest, ProfileResponse


def test_profile_duplicate_endpoint_uses_source_id() -> None:
    endpoint = ProfilesClient._duplicate_profile_endpoint("notte-profile-source")

    assert endpoint.method == "POST"
    assert endpoint.path == "notte-profile-source/duplicate"
    assert endpoint.response is ProfileResponse


def test_profile_duplicate_sends_optional_destination_name() -> None:
    client = NotteClient(api_key="test-api-key", server_url="https://api.notte.cc")
    expected = ProfileResponse(
        profile_id="notte-profile-copy",
        name="Copied login",
        created_at=dt.datetime(2026, 7, 27, tzinfo=dt.UTC),
        updated_at=dt.datetime(2026, 7, 27, tzinfo=dt.UTC),
    )

    with patch.object(client.profiles, "request", return_value=expected) as request:
        result = client.profiles.duplicate("notte-profile-source", name="Copied login")

    assert result is expected
    endpoint = request.call_args.args[0]
    assert endpoint.path == "notte-profile-source/duplicate"
    assert endpoint.request == ProfileDuplicateRequest(name="Copied login")
