from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from notte_sdk.endpoints.files import FileStorageClient, RemoteFileStorage
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import FileSource, SessionFile, SessionFilesPage

from tests.sdk.test_generated_endpoints import fake


@pytest.fixture
def files_client() -> FileStorageClient:
    with patch.object(FileStorageClient, "check_and_warn_version_mismatch"):
        return FileStorageClient(
            Mock(),
            api_key="test-api-key",  # pragma: allowlist secret
            server_url="https://api.notte.test",
        )


def file_metadata() -> SessionFile:
    return SessionFile.model_validate(
        {
            "id": "file-id",
            "session_id": "session-id",
            "filename": "input.txt",
            "mime_type": "text/plain",
            "size": 5,
            "checksum": "a" * 64,
            "created_at": "2026-08-21T00:00:00Z",
            "expires_at": "2026-08-22T00:00:00Z",
            "source": "user_upload",
        }
    )


def test_every_operation_requires_a_session(files_client: FileStorageClient) -> None:
    storage = RemoteFileStorage(_client=files_client)
    with pytest.raises(ValueError, match="session ID"):
        storage.list()


def test_list_uses_session_endpoint(files_client: FileStorageClient, monkeypatch: pytest.MonkeyPatch) -> None:
    session = fake(
        monkeypatch,
        {
            "files": [file_metadata().model_dump(mode="json")],
            "total": 1,
            "limit": 100,
            "offset": 0,
        },
    )
    result = files_client.list("session-id", source=FileSource.USER_UPLOAD)
    assert isinstance(result, SessionFilesPage)
    assert result.files[0].id == "file-id"
    assert session.calls[0].url == "https://api.notte.test/sessions/session-id/files"
    assert session.calls[0].params == {"source": "user_upload"}


def test_download_is_id_based(files_client: FileStorageClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, b"hello")
    with patch.object(files_client, "metadata", return_value=file_metadata()):
        destination = files_client.download("session-id", "file-id", str(tmp_path))

    assert Path(destination).read_bytes() == b"hello"
    assert [(c.method, c.url) for c in api.calls] == [
        ("GET", "https://api.notte.test/sessions/session-id/files/file-id")
    ]
    assert api.calls[0].headers["Authorization"] == "Bearer test-api-key"  # pragma: allowlist secret
    assert api.bodies[0].closed


def test_download_error_raises_api_error(
    files_client: FileStorageClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake(monkeypatch, {"detail": "File not found"}, 404)
    with patch.object(files_client, "metadata", return_value=file_metadata()):
        with pytest.raises(NotteAPIError) as error:
            _ = files_client.download("session-id", "file-id", str(tmp_path))

    assert error.value.status_code == 404
    assert error.value.error == {"detail": "File not found"}
    assert api.bodies[0].closed
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("filename", ["../../secret.txt", "..\\..\\secret.txt", "/tmp/secret.txt"])
def test_download_sanitizes_server_filename(
    files_client: FileStorageClient, tmp_path: Path, filename: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = fake(monkeypatch, b"hello")
    metadata = file_metadata().model_copy(update={"filename": filename})
    with patch.object(files_client, "metadata", return_value=metadata):
        destination = files_client.download("session-id", "file-id", str(tmp_path))

    assert Path(destination) == tmp_path / "secret.txt"
    assert Path(destination).read_bytes() == b"hello"


def test_download_does_not_follow_predictable_temporary_symlink(
    files_client: FileStorageClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("safe")
    (tmp_path / ".input.txt.part").symlink_to(outside)
    _ = fake(monkeypatch, b"download")
    with patch.object(files_client, "metadata", return_value=file_metadata()):
        destination = files_client.download("session-id", "file-id", str(tmp_path))

    assert Path(destination).read_bytes() == b"download"
    assert outside.read_text() == "safe"


def test_remote_storage_upload_is_session_scoped(files_client: FileStorageClient, tmp_path: Path) -> None:
    local = tmp_path / "input.txt"
    local.write_text("hello")
    metadata = file_metadata()
    with patch.object(files_client, "upload", return_value=metadata) as upload:
        result = RemoteFileStorage("session-id", _client=files_client).upload(str(local))

    assert result == metadata
    upload.assert_called_once_with("session-id", str(local), None)


def test_remote_storage_is_cloned_when_reused_across_sessions(files_client: FileStorageClient) -> None:
    storage = RemoteFileStorage(_client=files_client)

    first = storage.for_session("session-a")
    second = storage.for_session("session-b")

    assert first is storage
    assert first.session_id == "session-a"
    assert second is not storage
    assert second.session_id == "session-b"
    assert second.client is storage.client
