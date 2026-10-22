"""The clients built on the generated endpoints send the same requests as before.

The one wire change: list calls use the spec's path (`GET /personas`), not `GET /personas/`.
"""

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from email.message import Message
from email.parser import BytesParser
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest
from notte_sdk import NotteClient
from notte_sdk._generated import endpoints as page_api
from notte_sdk._generated import operations as api
from notte_sdk.endpoints.base import RawResponse
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import GetCredentialsRequest
from pydantic_core import to_json

SERVER = "https://api.example.test"


# Headers httpx adds to every request; `Call.headers` keeps only those the SDK sets.
TRANSPORT_HEADERS = frozenset({"host", "accept", "accept-encoding", "connection", "user-agent", "content-length"})


def parse_multipart(request: httpx.Request) -> tuple[dict[str, str], dict[str, tuple[str, bytes, str | None]]]:
    """Form fields and file parts (filename, content, content type) of a multipart body."""
    head = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
    message = BytesParser().parsebytes(head + request.content)
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes, str | None]] = {}
    for part in message.get_payload():
        assert isinstance(part, Message)
        name = part.get_param("name", header="content-disposition")
        assert isinstance(name, str)
        content = part.get_payload(decode=True)
        assert isinstance(content, bytes)
        filename = part.get_filename()
        if filename is None:
            fields[name] = content.decode()
        else:
            files[name] = (filename, content, part.get("content-type"))
    return fields, files


@dataclass
class Call:
    method: str
    url: str
    params: dict[str, Any]
    # The JSON text, the multipart form fields, or None without a body.
    data: Any
    headers: dict[str, str]
    files: dict[str, tuple[str, bytes, str | None]] = field(default_factory=dict)
    timeout: dict[str, float | None] = field(default_factory=dict)

    @classmethod
    def from_request(cls, request: httpx.Request) -> "Call":
        """What reached the wire: the URL without its query, the query parameters and the body."""
        params: dict[str, Any] = {}
        for key, value in parse_qsl(request.url.query.decode(), keep_blank_values=True):
            previous = params.get(key)
            params[key] = (
                value if previous is None else [*(previous if isinstance(previous, list) else [previous]), value]
            )
        headers = {
            name.decode(): value.decode()
            for name, value in request.headers.raw
            if name.decode().lower() not in TRANSPORT_HEADERS
            and not (name.lower() == b"content-type" and value.startswith(b"multipart/form-data"))
        }
        data: Any = request.content.decode() if request.content else None
        files: dict[str, tuple[str, bytes, str | None]] = {}
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            data, files = parse_multipart(request)
        return cls(
            method=request.method,
            url=str(request.url.copy_with(query=None)),
            params=params,
            data=data,
            headers=headers,
            files=files,
            timeout=request.extensions.get("timeout", {}),
        )


class Body(httpx.SyncByteStream):
    """A response body that records whether the SDK closed it."""

    def __init__(self, content: bytes) -> None:
        self.content: bytes = content
        self.closed: bool = False

    def __iter__(self) -> Iterator[bytes]:
        yield self.content

    def close(self) -> None:
        self.closed = True


class FakeSession:
    """Answers every SDK request in place of the API and records it.

    A `bytes` payload is sent as is; anything else as JSON.
    """

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.payload: Any = payload
        self.status_code: int = status_code
        self.calls: list[Call] = []
        self.requests: list[httpx.Request] = []
        self.bodies: list[Body] = []
        self.client: httpx.Client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.calls.append(Call.from_request(request))
        if isinstance(self.payload, bytes):
            content, headers = self.payload, {"content-type": "application/octet-stream"}
        else:
            # The API's JSON encoding: datetimes as ISO 8601, bytes as base64. A 204 has no body.
            content = b"" if self.status_code == 204 else to_json(self.payload, bytes_mode="base64")
            headers = {"content-type": "application/json"}
        body = Body(content)
        self.bodies.append(body)
        return httpx.Response(self.status_code, headers=headers, stream=body)


@pytest.fixture
def client() -> NotteClient:
    return NotteClient(api_key="test-api-key", server_url=SERVER)  # pragma: allowlist secret


def fake(monkeypatch: pytest.MonkeyPatch, payload: Any, status_code: int = 200) -> FakeSession:
    session = FakeSession(payload, status_code)
    monkeypatch.setattr("notte_sdk._transport.SharedHttpClient.get", lambda _: session.client)
    return session


PERSONA = {
    "persona_id": "persona-1",
    "status": "active",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.test",
    "internal_email": "persona-1@example.test",
    "vault_id": None,
    "phone_number": None,
    "created_at": "2026-10-13T00:00:00Z",
}
PROFILE = {
    "profile_id": "profile-1",
    "name": "p",
    "created_at": "2026-10-13T00:00:00Z",
    "updated_at": "2026-10-13T00:00:00Z",
}
VAULT = {"vault_id": "vault-1", "name": "v", "created_at": "2026-10-13T00:00:00Z"}


def test_generated_paths_start_at_the_server_root(client: NotteClient) -> None:
    # The client's base path ("profiles") is not prepended to absolute, generated paths.
    assert client.profiles.request_path(api.profile_get("profile-1")) == f"{SERVER}/profiles/profile-1"
    assert client.sessions.request_path(api.persona_get("p")) == f"{SERVER}/personas/p"


def test_path_parameters_are_one_segment() -> None:
    assert api.persona_get("a/b?c").path == "/personas/a%2Fb%3Fc"


def test_persona_requests(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    session = fake(monkeypatch, PERSONA)
    assert client.personas.get("persona-1").persona_id == "persona-1"
    _ = client.personas.create(create_vault=False)
    session.payload = {"items": [PERSONA], "page": 1, "page_size": 10}
    assert [p.persona_id for p in client.personas.list(page_size=10)] == ["persona-1"]
    session.payload = []
    assert client.personas.emails_list("persona-1", only_unread=True, limit=5) == []
    assert client.personas.sms_list("persona-1") == []
    session.payload = {"status": "success", "message": "deleted"}
    _ = client.personas.delete("persona-1")
    session.payload = {"phone_number": "+1555", "status": "success"}
    _ = client.personas.create_number("persona-1")
    session.payload = {"status": "success", "message": "deleted"}
    _ = client.personas.delete_number("persona-1")

    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in session.calls] == [
        ("GET", "/personas/persona-1", {}),
        ("POST", "/personas/create", {}),
        ("GET", "/personas", {"page_size": "10"}),
        ("GET", "/personas/persona-1/emails", {"limit": "5", "only_unread": "True"}),
        ("GET", "/personas/persona-1/sms", {}),
        ("DELETE", "/personas/persona-1", {}),
        ("POST", "/personas/persona-1/sms/number", {}),
        ("DELETE", "/personas/persona-1/sms/number", {}),
    ]
    assert json.loads(session.calls[1].data) == {"create_vault": False}


def test_profile_requests(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    session = fake(monkeypatch, PROFILE)
    assert client.profiles.create(name="p").profile_id == "profile-1"
    _ = client.profiles.get("profile-1")
    session.payload = {"items": [PROFILE], "page": 1, "page_size": 20}
    assert len(client.profiles.list(name="p")) == 1
    session.payload = {"success": True, "message": "deleted"}
    assert client.profiles.delete("profile-1") is True

    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in session.calls] == [
        ("POST", "/profiles/create", {}),
        ("GET", "/profiles/profile-1", {}),
        ("GET", "/profiles", {"page_size": "20", "name": "p"}),
        ("DELETE", "/profiles/profile-1", {}),
    ]


def test_vault_requests(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # In CI, tests/conftest.py wraps `VaultsClient.create` to record created vault ids for the end-of-run
    # cleanup. These vaults are fake, so keep their ids out of that list.
    scope = sys.modules.get("ci_vault_scope")
    if scope is not None:
        monkeypatch.setattr(scope, "record_vault_id", lambda _prefix, _vault_id: None)
    session = fake(monkeypatch, VAULT)
    url = GetCredentialsRequest(url="https://www.notte.cc/login").url
    assert client.vaults.create(name="v").vault_id == "vault-1"
    session.payload = {"items": [VAULT], "page": 1, "page_size": 10}
    assert len(client.vaults.list()) == 1
    session.payload = {"credentials": []}
    _ = client.vaults.credentials_list("vault-1")
    session.payload = {"credentials": {"email": "a@example.test", "password": "pw"}}  # pragma: allowlist secret
    _ = client.vaults.credentials_get("vault-1", url="https://www.notte.cc/login")
    session.payload = {"status": "success", "message": "ok"}
    _ = client.vaults.credentials_delete("vault-1", url="https://www.notte.cc/login")
    _ = client.vaults.credit_card_delete("vault-1")
    _ = client.vaults.delete("vault-1")

    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in session.calls] == [
        ("POST", "/vaults/create", {}),
        ("GET", "/vaults", {}),
        ("GET", "/vaults/vault-1", {}),
        ("GET", "/vaults/vault-1/credentials", {"url": url}),
        ("DELETE", "/vaults/vault-1/credentials", {"url": url}),
        ("DELETE", "/vaults/vault-1/card", {}),
        ("DELETE", "/vaults/vault-1", {}),
    ]


def test_errors_name_the_generated_path(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = fake(monkeypatch, {"detail": "Persona persona-1 not found"}, status_code=404)
    with pytest.raises(NotteAPIError) as error:
        _ = client.personas.get("persona-1")
    assert "personas/persona-1" in str(error.value)
    assert "personas//" not in str(error.value)


def test_raw_response_keeps_every_field(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = fake(monkeypatch, {"status": "ok", "version": "1"})
    response = client.sessions.request(page_api.health_check())
    assert isinstance(response, RawResponse)
    assert response.model_dump() == {"status": "ok", "version": "1"}
