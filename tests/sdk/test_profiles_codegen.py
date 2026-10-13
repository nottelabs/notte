"""Profiles compatibility captures, first run against the pre-migration facade."""

import json
from typing import Any

import pytest
from notte_core import __version__
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import ProfileCreateRequest, ProfileListRequest, ProfileResponse
from pydantic import ValidationError

from tests.sdk.test_generated_endpoints import PROFILE, SERVER, fake


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> NotteClient:
    monkeypatch.setattr("notte_sdk.endpoints.base.BaseClient.check_and_warn_version_mismatch", lambda _: None)
    monkeypatch.delenv("NOTTE_DB_PREVIEW_BRANCH", raising=False)
    monkeypatch.delenv("NOTTE_AUTH_CAPABILITY", raising=False)
    return NotteClient(api_key="test-api-key", server_url=SERVER)  # pragma: allowlist secret


def test_profile_wire_contract(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    monkeypatch.setattr("notte_core.common.telemetry._capture_usage_event", lambda name, **_: events.append(name))
    session = fake(monkeypatch, PROFILE)
    assert isinstance(client.profiles.create(), ProfileResponse)
    _ = client.profiles.create(name="p")
    _ = client.profiles.get("a/b ?#%é")
    session.payload = {"items": [PROFILE], "page": 1, "page_size": 20, "total": 1}
    profiles = client.profiles.list()
    assert len(profiles) == 1 and isinstance(profiles[0], ProfileResponse)
    assert profiles[0].persisted_domains == []
    _ = client.profiles.list(page=2, page_size=3, name="p")
    session.payload = []
    assert client.profiles.list() == []
    session.payload = {"success": False, "message": "not deleted"}
    assert client.profiles.delete("a/b") is False
    session.payload = {"success": True, "message": "deleted"}
    assert client.profiles.delete("a/b") is True

    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in session.calls] == [
        ("POST", "/profiles/create", None),
        ("POST", "/profiles/create", None),
        ("GET", "/profiles/a%2Fb%20%3F%23%25%C3%A9", None),
        ("GET", "/profiles", {"page": 1, "page_size": 20}),
        ("GET", "/profiles", {"page": 2, "page_size": 3, "name": "p"}),
        ("GET", "/profiles", {"page": 1, "page_size": 20}),
        ("DELETE", "/profiles/a%2Fb", None),
        ("DELETE", "/profiles/a%2Fb", None),
    ]
    assert json.loads(session.calls[0].data) == {}
    assert json.loads(session.calls[1].data) == {"name": "p"}
    for call in session.calls:
        assert call.headers == {
            "Authorization": "Bearer test-api-key",  # pragma: allowlist secret
            "x-notte-sdk-version": __version__,
            "x-notte-request-origin": "sdk-python",
            **({"Content-Type": "application/json"} if call.method == "POST" else {}),
        }
    assert events == [
        f"cloud.profile.{name}" for name in ["create", "create", "get", "list", "list", "list", "delete", "delete"]
    ]


@pytest.mark.parametrize("method", ["get", "delete"])
def test_profile_404(client: NotteClient, monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    _ = fake(monkeypatch, {"detail": "Profile missing"}, status_code=404)
    with pytest.raises(NotteAPIError) as error:
        _ = getattr(client.profiles, method)("missing/id")
    assert error.value.status_code == 404
    assert error.value.error == {"detail": "Profile missing"}
    assert "profiles/missing%2Fid" in str(error.value)


@pytest.mark.parametrize("method", ["create", "get", "list"])
def test_profile_defaults_and_explicit_null(client: NotteClient, monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    session = fake(monkeypatch, PROFILE)

    def fetch(payload: dict[str, Any]) -> ProfileResponse:
        session.payload = {"items": [payload]} if method == "list" else payload
        if method == "list":
            return client.profiles.list()[0]
        if method == "create":
            return client.profiles.create()
        return client.profiles.get("profile-1")

    first, second = fetch(PROFILE), fetch(PROFILE)
    assert first.persisted_domains == second.persisted_domains == []
    first.persisted_domains.append("example.com")
    assert second.persisted_domains == []
    assert fetch({**PROFILE, "persisted_domains": ["example.com"]}).persisted_domains == ["example.com"]
    with pytest.raises(ValidationError, match="persisted_domains"):
        _ = fetch({**PROFILE, "persisted_domains": None})


def test_request_compatibility(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    session = fake(monkeypatch, PROFILE)
    assert ProfileCreateRequest.model_validate({"name": None}).model_dump(exclude_none=True) == {}
    assert ProfileListRequest().model_dump(exclude_none=True) == {"page": 1, "page_size": 20}
    for cls in (ProfileCreateRequest, ProfileListRequest):
        with pytest.raises(ValidationError):
            _ = cls.model_validate({"typo": True})
    for field in ("only_active", "only_current_token"):
        with pytest.raises(ValidationError):
            _ = ProfileListRequest.model_validate({field: True})
    # The facade historically leaves pagination bounds to the server.
    session.payload = {"items": []}
    _ = client.profiles.list(page=0, page_size=101)
    assert session.calls[-1].params == {"page": 0, "page_size": 101}


@pytest.mark.parametrize("payload", [{}, {"success": True}, {"message": "deleted"}])
def test_incomplete_delete_response_is_not_success(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    _ = fake(monkeypatch, payload)
    with pytest.raises(ValidationError):
        _ = client.profiles.delete("profile-1")
