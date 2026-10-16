"""JSON file-operation captures, first run against the old HTTP facade."""

from typing import Any

import pytest
import requests
from notte_core import __version__
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import FileSource, SessionFilesPage

from tests.sdk.test_file_storage import file_metadata
from tests.sdk.test_generated_endpoints import SERVER, FakeSession, fake
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client


def capture(monkeypatch: pytest.MonkeyPatch, payload: Any, status: int = 200) -> FakeSession:
    session = fake(monkeypatch, payload, status)

    def send(method: str, url: str, **kwargs: Any) -> requests.Response:
        recorded = session._call(method, url, **kwargs)
        response = requests.Response()
        response.status_code = recorded.status_code
        response._content = recorded.content
        return response

    monkeypatch.setattr("notte_sdk.endpoints.files.requests.get", lambda url, **kw: send("GET", url, **kw))
    monkeypatch.setattr("notte_sdk.endpoints.files.requests.delete", lambda url, **kw: send("DELETE", url, **kw))
    return session


def test_files_json_wire_contract(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    monkeypatch.setattr("notte_core.telemetry._capture_usage_event", lambda name, **_: events.append(name))
    page = {"files": [file_metadata().model_dump(mode="json")], "total": 4, "limit": 100, "offset": 0}
    session = capture(monkeypatch, page)
    result = client.files.list("session-id")
    assert isinstance(result, SessionFilesPage)
    assert result.total == 4
    assert result.files[0].source is FileSource.USER_UPLOAD
    _ = client.files.list("session-id", source=FileSource.SESSION_DOWNLOAD, limit=0, offset=-1)
    _ = client.files.list("session-id", source="invalid")
    session.status_code = 204
    session.payload = None
    assert client.files.delete("session-id", "file-id") is None
    assert [(c.method, c.url.removeprefix(SERVER), c.params, c.data) for c in session.calls] == [
        ("GET", "/sessions/session-id/files", {}, None),
        ("GET", "/sessions/session-id/files", {"limit": 0, "offset": -1, "source": "session_download"}, None),
        ("GET", "/sessions/session-id/files", {"source": "invalid"}, None),
        ("DELETE", "/sessions/session-id/files/file-id", None, None),
    ]
    assert events == ["cloud.files.list"] * 3 + ["cloud.files.delete"]
    for call in session.calls:
        assert call.headers == {
            "Authorization": "Bearer test-api-key",  # pragma: allowlist secret
            "x-notte-sdk-version": __version__,
            "x-notte-request-origin": "sdk-python",
        }


@pytest.mark.parametrize("status", [404, 422])
@pytest.mark.parametrize("method", ["list", "delete"])
def test_files_api_errors(client: NotteClient, monkeypatch: pytest.MonkeyPatch, status: int, method: str) -> None:
    session = capture(monkeypatch, {"detail": "file error"}, status)
    with pytest.raises(NotteAPIError) as error:
        if method == "list":
            _ = client.files.list("session-id", limit=0)
        else:
            client.files.delete("session-id", "file-id")
    assert error.value.status_code == status
    assert error.value.error == {"detail": "file error"}
    assert len(session.calls) == 1


def test_file_metadata_pagination(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    offsets: list[int] = []
    target = file_metadata()
    other = target.model_copy(update={"id": "other"})

    def page(session_id: str, *, limit: int, offset: int) -> SessionFilesPage:
        assert session_id == "session-id"
        assert limit == 1000
        offsets.append(offset)
        return SessionFilesPage(files=[other if offset == 0 else target], total=2, limit=limit, offset=offset)

    monkeypatch.setattr(client.files, "list", page)
    assert client.files.metadata("session-id", "file-id") is target
    assert offsets == [0, 1]
    with pytest.raises(FileNotFoundError):
        _ = client.files.metadata("session-id", "missing")


def test_files_encode_path_segments(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    session = capture(monkeypatch, {"files": [], "total": 0, "limit": 100, "offset": 0})
    _ = client.files.list("a/b ?#%é")
    session.status_code = 204
    client.files.delete("a/b ?#%é", "x/y")
    assert [c.url.removeprefix(SERVER) for c in session.calls] == [
        "/sessions/a%2Fb%20%3F%23%25%C3%A9/files",
        "/sessions/a%2Fb%20%3F%23%25%C3%A9/files/x%2Fy",
    ]


def test_file_types_derive_from_generated_models() -> None:
    from notte_sdk._generated import models
    from notte_sdk.types import SessionFile

    assert issubclass(SessionFile, models.SessionFile)
    assert issubclass(SessionFilesPage, models.SessionFilesPage)
    assert {member.value for member in FileSource} == {member.value for member in models.FileSource}


def test_file_enum_is_generated_with_public_member_names() -> None:
    from notte_sdk._generated import models

    assert FileSource is models.FileSource
    assert FileSource.USER_UPLOAD.value == "user_upload"
    assert FileSource.USER_UPLOAD == "user_upload"
    assert isinstance(FileSource.USER_UPLOAD, str)
