from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from notte_core.common.cache import CacheDirectory, ensure_cache_directory
from notte_core.common.telemetry import track_usage
from notte_core.storage import BaseStorage
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import (
    DownloadFileRequest,
    FileLinkResponse,
    FileUploadResponse,
    ListFilesResponse,
)

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


def _get_cache_dir() -> Path:
    """Get cache directory with NOTTE_CACHE_DIR override support."""
    # Support NOTTE_CACHE_DIR override for backward compatibility
    env_cache_dir = os.getenv("NOTTE_CACHE_DIR")
    if env_cache_dir:
        return Path(env_cache_dir)
    # Use centralized cache directory
    return ensure_cache_directory(CacheDirectory.FILES)


NOTTE_CACHE_DIR: Path = _get_cache_dir()


@final
class FileStorageClient(BaseClient):
    """
    Client for Notte Storage API.
    """

    STORAGE_UPLOAD = "uploads/{file_name}"
    STORAGE_UPLOAD_LIST = "uploads"
    STORAGE_DOWNLOAD = "{session_id}/downloads/{file_name}"
    STORAGE_UPLOAD_DOWNLOADED_FILE = "{session_id}/downloads/{file_name}"
    STORAGE_DOWNLOAD_LIST = "{session_id}/downloads"

    def __init__(
        self, root_client: NotteClient, api_key: str | None = None, server_url: str | None = None, verbose: bool = False
    ):
        """
        Initialize a FileStorageClient instance.

        Initializes the client with an optional API key and server URL,
        setting the base endpoint to "storage".
        """
        super().__init__(
            root_client=root_client,
            base_endpoint_path="storage",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _storage_upload_endpoint(file_name: str | None = None) -> NotteEndpoint[FileUploadResponse]:
        """
        Returns a NotteEndpoint for uploading files to storage.
        """
        path = FileStorageClient.STORAGE_UPLOAD
        if file_name is not None:
            path = path.format(file_name=file_name)
        return NotteEndpoint(path=path, response=FileUploadResponse, method="POST")

    @staticmethod
    def _storage_upload_list_endpoint() -> NotteEndpoint[ListFilesResponse]:
        """
        Returns a NotteEndpoint for listing upload files from storage.
        """
        path = FileStorageClient.STORAGE_UPLOAD_LIST
        return NotteEndpoint(path=path, response=ListFilesResponse, method="GET")

    @staticmethod
    def _storage_download_endpoint(
        session_id: str | None = None, file_name: str | None = None
    ) -> NotteEndpoint[FileLinkResponse]:
        """
        Returns a NotteEndpoint for getting a file link for download from storage.
        """
        path = FileStorageClient.STORAGE_DOWNLOAD
        if session_id is not None and file_name is not None:
            path = path.format(session_id=session_id, file_name=file_name)
        return NotteEndpoint(path=path, response=FileLinkResponse, method="GET")

    @staticmethod
    def _storage_upload_downloaded_file_endpoint(
        session_id: str | None = None, file_name: str | None = None
    ) -> NotteEndpoint[FileUploadResponse]:
        """
        Returns a NotteEndpoint for getting a file link for download from storage.
        """
        path = FileStorageClient.STORAGE_UPLOAD_DOWNLOADED_FILE
        if session_id is not None and file_name is not None:
            path = path.format(session_id=session_id, file_name=file_name)
        return NotteEndpoint(path=path, response=FileUploadResponse, method="POST")

    @staticmethod
    def _storage_download_list_endpoint(session_id: str | None = None) -> NotteEndpoint[ListFilesResponse]:
        """
        Returns a NotteEndpoint for listing download files from storage.
        """
        path = FileStorageClient.STORAGE_DOWNLOAD_LIST
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ListFilesResponse, method="GET")

    def _upload_file(self, file_path: str, endpoint: NotteEndpoint[FileUploadResponse]):
        if not Path(file_path).exists():
            raise FileNotFoundError(
                f"Cannot upload file {file_path} because it does not exist in the local file system."
            )
        return self.request(endpoint.with_file(file_path))

    @track_usage("cloud.files.upload")
    def upload(self, file_path: str, upload_file_name: str | None = None) -> FileUploadResponse:
        """
        Upload a file to storage.

        Args:
            file_path: The path to the file to upload.
            upload_file_name: The name of the file to upload. If not provided, the file name will be the same as the file path.
        """
        file_name = upload_file_name or Path(file_path).name
        return self._upload_file(file_path=file_path, endpoint=self._storage_upload_endpoint(file_name=file_name))

    @track_usage("cloud.files.upload_downloaded_file")
    def upload_downloaded_file(
        self, session_id: str, file_path: str, upload_file_name: str | None = None
    ) -> FileUploadResponse:
        """
        Upload a file to storage.

        Args:
            file_path: The path to the file to upload.
            upload_file_name: The name of the file to upload. If not provided, the file name will be the same as the file path.
        """
        file_name = upload_file_name or Path(file_path).name
        return self._upload_file(
            file_path=file_path,
            endpoint=self._storage_upload_downloaded_file_endpoint(session_id=session_id, file_name=file_name),
        )

    @track_usage("cloud.files.download")
    def download(self, session_id: str, file_name: str, local_dir: str, force: bool = False) -> bool:
        """
        Downloads a file from storage for the current session.

        Args:
            file_name: The name of the file to download.
            local_dir: The directory to download the file to.
            force: Whether to overwrite the file if it already exists.

        Returns:
            True if the file was downloaded successfully, False otherwise.
        """

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

    def list_uploaded_files(self) -> list[str]:
        """
        List files in storage. 'type' can be 'uploads' or 'downloads'.
        """
        endpoint = self._storage_upload_list_endpoint()
        resp: ListFilesResponse = self.request(endpoint)
        return resp.files

    def list_downloaded_files(self, session_id: str) -> list[str]:
        """
        List files in storage. 'type' can be 'uploads' or 'downloads'.
        """

        endpoint = self._storage_download_list_endpoint(session_id=session_id)
        resp_dl: ListFilesResponse = self.request(endpoint)
        return resp_dl.files


class RemoteFileStorage(BaseStorage):
    def __init__(self, session_id: str | None = None, *, _client: FileStorageClient | None = None):
        if _client is None:
            raise ValueError("FileStorageClient is required")
        self.client: FileStorageClient = _client
        super().__init__(upload_dir=str(NOTTE_CACHE_DIR / "uploads"), download_dir=str(NOTTE_CACHE_DIR / "downloads"))
        self._session_id: str | None = session_id

    def set_session_id(self, id: str) -> None:
        self._session_id = id

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            raise ValueError("Session ID is not set. Call set_session_id() to set the session ID.")
        return self._session_id

    def download(self, file_name: str, local_dir: str, force: bool = False) -> bool:
        """
        Stores a file that has been downloaded from a website in the current session.

        ```python
        file_storage = notte.FileStorage("<session_id>")
        # file.pdf has been downloaded by an agent in the session
        # you can download it to your local machine using:
        file_storage.download(file_name="file.pdf", local_dir="<local_download_dir>")
        ```

        """
        return self.client.download(session_id=self.session_id, file_name=file_name, local_dir=local_dir, force=force)

    def upload(self, file_path: str, upload_file_name: str | None = None) -> bool:
        """
        Upload a file from your local machine to storage.

        This file will then be available to the agent in the current session.

        ```python
        storage = notte.FileStorage()
        with notte.Session(storage=storage) as session:
            # make the file available to the agent in the current session
            storage.upload(file_path="<local_file_path>")
        ```

        """
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
    async def alist_uploaded_files(self) -> list[str]:
        """
        List files that have been uploaded to storage.

        ```python
        storage = notte.FileStorage()
        # list the files that have been uploaded to storage
        files = storage.list_uploaded_files()
        ```
        """
        return self.client.list_uploaded_files()

    @override
    async def alist_downloaded_files(self) -> list[str]:
        """
        List files that have been downloaded into storage by the agents.

        ```python
        storage = notte.FileStorage(session_id="<session_id>")
        # list the files that have been downloaded from storage
        files = storage.list_downloaded_files()
        ```
        """
        return self.client.list_downloaded_files(session_id=self.session_id)
