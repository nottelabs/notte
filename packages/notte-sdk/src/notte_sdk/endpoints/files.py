from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel
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


@final
class FileStorageClient(BaseClient):
    """
    Client for Notte Storage API.
    """

    STORAGE_UPLOAD = "uploads/{file_name}"
    STORAGE_UPLOAD_LIST = "uploads"
    STORAGE_DOWNLOAD = "{session_id}/downloads/{file_name}"
    STORAGE_DOWNLOAD_LIST = "{session_id}/downloads"

    def __init__(
        self,
        root_client: NotteClient,
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
        session_id: str | None = None,
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
        self.session_id = session_id

    def set_session_id(self, id: str) -> None:
        self.session_id = id

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
    def _storage_download_list_endpoint(session_id: str | None = None) -> NotteEndpoint[ListFilesResponse]:
        """
        Returns a NotteEndpoint for listing download files from storage.
        """
        path = FileStorageClient.STORAGE_DOWNLOAD_LIST
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ListFilesResponse, method="GET")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        return [
            FileStorageClient._storage_upload_endpoint(),
            FileStorageClient._storage_download_endpoint(),
            FileStorageClient._storage_upload_list_endpoint(),
            FileStorageClient._storage_download_list_endpoint(),
        ]

    def upload(self, file_path: str, upload_file_name: str | None = None) -> FileUploadResponse:
        """
        Upload a file to storage.

        Args:
            file_path: The path to the file to upload.
            upload_file_name: The name of the file to upload. If not provided, the file name will be the same as the file path.
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(
                f"Cannot upload file {file_path} because it does not exist in the local file system."
            )

        upload_file_name = upload_file_name or Path(file_path).name
        endpoint = self._storage_upload_endpoint(file_name=upload_file_name)
        return self.request(endpoint.with_file(file_path))

    def download(self, file_name: str, local_dir: str, force: bool = False) -> bool:
        """
        Downloads a file from storage for the current session.

        Args:
            file_name: The name of the file to download.
            local_dir: The directory to download the file to.
            force: Whether to overwrite the file if it already exists.

        Returns:
            True if the file was downloaded successfully, False otherwise.
        """
        if not self.session_id:
            raise ValueError("File object not attached to a Session!")

        local_dir_path = Path(local_dir)
        if not local_dir_path.exists():
            local_dir_path.mkdir(parents=True, exist_ok=True)

        file_path = local_dir_path / file_name

        if file_path.exists() and not force:
            raise ValueError(f"A file with name '{file_name}' is already at the path! Use force=True to overwrite.")

        endpoint = self._storage_download_endpoint(session_id=self.session_id, file_name=file_name)
        _ = DownloadFileRequest.model_validate({"filename": file_name})
        resp: FileLinkResponse = self.request(endpoint)
        return self.request_download(resp.url, str(file_path))

    def list(self, type: str = "downloads") -> list[str]:
        """
        List files in storage. 'type' can be 'uploads' or 'downloads'.
        """
        if type == "uploads":
            endpoint = self._storage_upload_list_endpoint()
            resp: ListFilesResponse = self.request(endpoint)
        elif type == "downloads":
            if not self.session_id:
                raise ValueError("File object not attached to a Session!")

            endpoint = self._storage_download_list_endpoint(session_id=self.session_id)

            resp_dl: ListFilesResponse = self.request(endpoint)
            return resp_dl.files
        else:
            raise ValueError("type must be 'uploads' or 'downloads'")

        return resp.files


@final
class RemoteFileStorageFactory:
    def __init__(self, client: FileStorageClient):
        self.client = client

    def __call__(self, session_id: str | None = None) -> FileStorageClient:
        if session_id is not None:
            self.client.set_session_id(session_id)
        return self.client
