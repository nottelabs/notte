from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from notte_sdk.endpoints.files import FileStorageClient, RemoteFileStorage
from notte_sdk.types import FileLinkResponse


@pytest.fixture
def files_client() -> FileStorageClient:
    with patch.object(FileStorageClient, "check_and_warn_version_mismatch"):
        return FileStorageClient(
            root_client=Mock(),
            api_key="test-api-key",  # pragma: allowlist secret
            server_url="https://api.notte.test",
        )


def test_uploaded_file_download_endpoint() -> None:
    endpoint = FileStorageClient._storage_uploaded_file_download_endpoint("input.txt")

    assert endpoint.path == "uploads/input.txt"
    assert endpoint.method == "GET"
    assert endpoint.response is FileLinkResponse


def test_download_uploaded_file(files_client: FileStorageClient, tmp_path: Path) -> None:
    response = FileLinkResponse(url="https://storage.notte.test/input.txt")

    with (
        patch.object(files_client, "request", return_value=response) as request,
        patch.object(files_client, "request_download", return_value=True) as request_download,
    ):
        result = files_client.download_uploaded_file(file_name="input.txt", local_dir=str(tmp_path))

    assert result is True
    endpoint = request.call_args.args[0]
    assert endpoint.path == "uploads/input.txt"
    assert endpoint.method == "GET"
    request_download.assert_called_once_with(response.url, str(tmp_path / "input.txt"))


def test_download_uploaded_file_refuses_to_overwrite(files_client: FileStorageClient, tmp_path: Path) -> None:
    file_path = tmp_path / "input.txt"
    _ = file_path.write_text("existing")

    with (
        patch.object(files_client, "request") as request,
        pytest.raises(ValueError, match="force=True"),
    ):
        files_client.download_uploaded_file(file_name=file_path.name, local_dir=str(tmp_path))

    request.assert_not_called()


@pytest.mark.parametrize(
    "file_name",
    [
        "../outside.txt",
        "/tmp/outside.txt",
        r"..\outside.txt",
        r"C:\tmp\outside.txt",
    ],
)
def test_download_uploaded_file_rejects_paths(
    files_client: FileStorageClient,
    tmp_path: Path,
    file_name: str,
) -> None:
    with (
        patch.object(files_client, "request") as request,
        patch.object(files_client, "request_download") as request_download,
        pytest.raises(ValueError, match="filename, not a path"),
    ):
        files_client.download_uploaded_file(
            file_name=file_name,
            local_dir=str(tmp_path),
            force=True,
        )

    request.assert_not_called()
    request_download.assert_not_called()


def test_remote_storage_downloads_uploaded_file_without_session(tmp_path: Path) -> None:
    client = Mock(spec=FileStorageClient)
    client.download_uploaded_file.return_value = True
    storage = RemoteFileStorage(_client=client)

    result = storage.download_uploaded_file(file_name="input.txt", local_dir=str(tmp_path), force=True)

    assert result is True
    client.download_uploaded_file.assert_called_once_with(
        file_name="input.txt",
        local_dir=str(tmp_path),
        force=True,
    )
