"""Async file storage endpoint client for the Notte SDK."""
# Auto-generated from _async/ - DO NOT EDIT DIRECTLY

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from notte_core.common.cache import CacheDirectory, ensure_cache_directory
from notte_core.common.telemetry import track_usage
from notte_core.storage import BaseStorage
from typing_extensions import final, override

from notte_sdk._sync.base import BaseClient, NotteEndpoint
from notte_sdk._sync.http import HTTPClient
from notte_sdk.types import (
    DownloadFileRequest,
    FileInfo,
    FileLinkResponse,
    FileUploadResponse,
    ListFilesResponse,
)

if TYPE_CHECKING:
    from notte_sdk._sync.client import NotteClient


def _get_cache_dir() -> Path:
    """Get cache directory with NOTTE_CACHE_DIR override support."""
    env_cache_dir = os.getenv("NOTTE_CACHE_DIR")
    if env_cache_dir:
        return Path(env_cache_dir)
    return ensure_cache_directory(CacheDirectory.FILES)


NOTTE_CACHE_DIR: Path = _get_cache_dir()


@final
class FileStorageClient(BaseClient):
    """Async client for Notte Storage API."""

    STORAGE_UPLOAD = "uploads/{file_name}"
    STORAGE_UPLOAD_LIST = "uploads"
    STORAGE_DOWNLOAD = "{session_id}/downloads/{file_name}"
    STORAGE_UPLOAD_DOWNLOADED_FILE = "{session_id}/downloads/{file_name}"
    STORAGE_DOWNLOAD_LIST = "{session_id}/downloads"

    def __init__(
        self,
        root_client: "NotteClient",
        http_client: HTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize FileStorageClient."""
        super().__init__(
            root_client=root_client,
            base_endpoint_path="storage",
            http_client=http_client,
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _storage_upload_endpoint(file_name: str | None = None) -> NotteEndpoint[FileUploadResponse]:
        path = FileStorageClient.STORAGE_UPLOAD
        if file_name is not None:
            path = path.format(file_name=file_name)
        return NotteEndpoint(path=path, response=FileUploadResponse, method="POST")

    @staticmethod
    def _storage_upload_list_endpoint() -> NotteEndpoint[ListFilesResponse]:
        path = FileStorageClient.STORAGE_UPLOAD_LIST
        return NotteEndpoint(path=path, response=ListFilesResponse, method="GET")

    @staticmethod
    def _storage_download_endpoint(
        session_id: str | None = None, file_name: str | None = None
    ) -> NotteEndpoint[FileLinkResponse]:
        path = FileStorageClient.STORAGE_DOWNLOAD
        if session_id is not None and file_name is not None:
            path = path.format(session_id=session_id, file_name=file_name)
        return NotteEndpoint(path=path, response=FileLinkResponse, method="GET")

    @staticmethod
    def _storage_upload_downloaded_file_endpoint(
        session_id: str | None = None, file_name: str | None = None
    ) -> NotteEndpoint[FileUploadResponse]:
        path = FileStorageClient.STORAGE_UPLOAD_DOWNLOADED_FILE
        if session_id is not None and file_name is not None:
            path = path.format(session_id=session_id, file_name=file_name)
        return NotteEndpoint(path=path, response=FileUploadResponse, method="POST")

    @staticmethod
    def _storage_download_list_endpoint(session_id: str | None = None) -> NotteEndpoint[ListFilesResponse]:
        path = FileStorageClient.STORAGE_DOWNLOAD_LIST
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ListFilesResponse, method="GET")

    def _upload_file(self, file_path: str, endpoint: NotteEndpoint[FileUploadResponse]) -> FileUploadResponse:
        if not Path(file_path).exists():
            raise FileNotFoundError(
                f"Cannot upload file {file_path} because it does not exist in the local file system."
            )
        return self.request(endpoint.with_file(file_path))

    @track_usage("cloud.files.upload")
    def upload(self, file_path: str, upload_file_name: str | None = None) -> FileUploadResponse:
        """Upload a file to storage."""
        file_name = upload_file_name or Path(file_path).name
        return self._upload_file(file_path=file_path, endpoint=self._storage_upload_endpoint(file_name=file_name))

    @track_usage("cloud.files.upload_downloaded_file")
    def upload_downloaded_file(
        self, session_id: str, file_path: str, upload_file_name: str | None = None
    ) -> FileUploadResponse:
        """Upload a downloaded file to storage."""
        file_name = upload_file_name or Path(file_path).name
        return self._upload_file(
            file_path=file_path,
            endpoint=self._storage_upload_downloaded_file_endpoint(session_id=session_id, file_name=file_name),
        )

    @track_usage("cloud.files.download")
    def download(self, session_id: str, file_name: str, local_dir: str, force: bool = False) -> bool:
        """Download a file from storage."""
        local_dir_path = Path(local_dir)
        if not local_dir_path.exists():
            local_dir_path.mkdir(parents=True, exist_ok=True)

        file_path = local_dir_path / file_name

        if file_path.exists() and not force:
            raise ValueError(f"A file with name '{file_name}' is already at the path! Use force=True to overwrite.")

        endpoint = self._storage_download_endpoint(session_id=session_id, file_name=file_name)
        _ = DownloadFileRequest.model_validate({"filename": file_name})
        resp: FileLinkResponse = self.request(endpoint)
        return self.request_download(resp.url, str(file_path))

    def list_uploaded_files(self) -> list[FileInfo]:
        """List uploaded files in storage."""
        endpoint = self._storage_upload_list_endpoint()
        resp: ListFilesResponse = self.request(endpoint)
        return resp.files

    def list_downloaded_files(self, session_id: str) -> list[FileInfo]:
        """List downloaded files in storage."""
        endpoint = self._storage_download_list_endpoint(session_id=session_id)
        resp_dl: ListFilesResponse = self.request(endpoint)
        return resp_dl.files


class RemoteFileStorage(BaseStorage):
    """Async remote file storage."""

    def __init__(self, session_id: str | None = None, *, _client: FileStorageClient | None = None):
        if _client is None:
            raise ValueError("FileStorageClient is required")
        self.client: FileStorageClient = _client
        super().__init__(upload_dir=str(NOTTE_CACHE_DIR / "uploads"), download_dir=str(NOTTE_CACHE_DIR / "downloads"))
        self._session_id: str | None = session_id

    @property
    @override
    def is_remote(self) -> bool:
        return True

    def set_session_id(self, id: str) -> None:
        self._session_id = id

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            raise ValueError("Session ID is not set. Call set_session_id() to set the session ID.")
        return self._session_id

    def download(self, file_name: str, local_dir: str, force: bool = False) -> bool:
        """Download a file from storage."""
        return self.client.download(session_id=self.session_id, file_name=file_name, local_dir=local_dir, force=force)

    def upload(self, file_path: str, upload_file_name: str | None = None) -> bool:
        """Upload a file to storage."""
        response = self.client.upload(file_path=file_path, upload_file_name=upload_file_name)
        return response.success

    @override
    async def get_file(self, name: str) -> str | None:
        assert self.download_dir is not None
        _ = Path(self.download_dir).mkdir(parents=True, exist_ok=True)

        status = self.client.download(session_id=self.session_id, file_name=name, local_dir=self.download_dir)
        if not status:
            return None
        return str(Path(self.download_dir) / name)

    @override
    async def set_file(self, path: str) -> bool:
        response = self.client.upload_downloaded_file(session_id=self.session_id, file_path=path)
        return response.success

    @override
    async def list_uploaded_files(self) -> list[FileInfo]:
        """List uploaded files in storage."""
        return self.client.list_uploaded_files()

    @override
    async def list_downloaded_files(self) -> list[FileInfo]:
        """List downloaded files in storage."""
        return self.client.list_downloaded_files(session_id=self.session_id)
