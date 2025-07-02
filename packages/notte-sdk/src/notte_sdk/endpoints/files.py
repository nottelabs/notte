from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from notte_core.common.resource import SyncResource
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import (
    DownloadFileRequest,
    FileLinkResponse,
    FileUploadResponse,
    ListFilesResponse,
)


@final
class FilesClient(BaseClient, SyncResource):
    """
    Client for Notte Storage API.
    """

    STORAGE_UPLOAD = "upload"
    STORAGE_UPLOAD_LIST = "upload/list"
    STORAGE_DOWNLOAD = "{session_id}/download"
    STORAGE_DOWNLOAD_LIST = "{session_id}/download/list"

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
        session_id: str | None = None,
    ):
        """
        Initialize a FilesClient instance.

        Initializes the client with an optional API key and server URL,
        setting the base endpoint to "storage".
        """
        super().__init__(base_endpoint_path="storage", server_url=server_url, api_key=api_key, verbose=verbose)
        self.session_id = session_id

    @override
    def start(self) -> None:
        pass

    @override
    def stop(self) -> None:
        pass

    def set_session_id(self, id: str) -> None:
        self.session_id = id

    @staticmethod
    def _storage_upload_endpoint() -> NotteEndpoint[FileUploadResponse]:
        """
        Returns a NotteEndpoint for uploading files to storage.
        """
        path = FilesClient.STORAGE_UPLOAD
        return NotteEndpoint(path=path, response=FileUploadResponse, method="POST")

    @staticmethod
    def _storage_upload_list_endpoint() -> NotteEndpoint[ListFilesResponse]:
        """
        Returns a NotteEndpoint for listing upload files from storage.
        """
        path = FilesClient.STORAGE_UPLOAD_LIST
        return NotteEndpoint(path=path, response=ListFilesResponse, method="GET")

    @staticmethod
    def _storage_download_endpoint(session_id: str | None = None) -> NotteEndpoint[FileLinkResponse]:
        """
        Returns a NotteEndpoint for getting a file link for download from storage.
        """
        path = FilesClient.STORAGE_DOWNLOAD
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=FileLinkResponse, method="GET")

    @staticmethod
    def _storage_download_list_endpoint(session_id: str | None = None) -> NotteEndpoint[ListFilesResponse]:
        """
        Returns a NotteEndpoint for listing download files from storage.
        """
        path = FilesClient.STORAGE_DOWNLOAD_LIST
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ListFilesResponse, method="GET")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        return [
            FilesClient._storage_upload_endpoint(),
            FilesClient._storage_download_endpoint(),
            FilesClient._storage_upload_list_endpoint(),
            FilesClient._storage_download_list_endpoint(),
        ]

    def upload(self, file_path: str) -> FileUploadResponse:
        """
        Upload a file to storage.
        """
        endpoint = FilesClient._storage_upload_endpoint()
        return self.request(endpoint.with_file(file_path))

    def download(self, file_name: str, local_path: str, force: bool = False) -> bool:
        """
        Downloads a file from storage for the current session.
        """
        if not self.session_id:
            raise ValueError("File object not attached to a Session!")

        file_path = f"{str(Path(local_path))}/{file_name}"

        if Path(file_path).exists() and not force:
            raise ValueError(f"A file with name '{file_name}' is already at the path! Use force=True to overwrite.")

        endpoint = FilesClient._storage_download_endpoint(session_id=self.session_id)
        params = DownloadFileRequest.model_validate({"filename": file_name})
        resp: FileLinkResponse = self.request(endpoint.with_params(params))
        return self.request_download(resp.url, file_path)

    def list(self, which: str = "downloads") -> list[str]:
        """
        List files in storage. 'which' can be 'uploads' or 'downloads'.
        """
        if which == "uploads":
            endpoint = FilesClient._storage_upload_list_endpoint()
        elif which == "downloads":
            endpoint = FilesClient._storage_download_list_endpoint(session_id=self.session_id)
        else:
            raise ValueError("which must be 'upload' or 'download'")
        resp: ListFilesResponse = self.request(endpoint)
        return resp.files


@final
class RemoteFilesFactory:
    def __init__(self, client: FilesClient):
        self.client = client

    def __call__(self, session_id: str | None = None) -> FilesClient:
        if session_id is not None:
            self.client.set_session_id(session_id)
        return self.client
