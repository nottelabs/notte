from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import (
    DownloadFileFallbackRequest,
    DownloadFileRequest,
    DownloadsListRequest,
    FileLinkResponse,
    FileUploadResponse,
    ListFilesResponse,
)


@final
class FileStorageClient(BaseClient):
    """
    Client for Notte Storage API.
    """

    STORAGE_UPLOAD = "upload"
    STORAGE_UPLOAD_LIST = "upload/list"
    STORAGE_DOWNLOAD = "{session_id}/download"
    STORAGE_DOWNLOAD_LIST = "{session_id}/download/list"
    STORAGE_DOWNLOAD_FB = "download"
    STORAGE_DOWNLOAD_LIST_FB = "download/list"

    def __init__(
        self,
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
        super().__init__(base_endpoint_path="storage", server_url=server_url, api_key=api_key, verbose=verbose)
        self.session_id = session_id

    def set_session_id(self, id: str) -> None:
        self.session_id = id

    @staticmethod
    def _storage_upload_endpoint() -> NotteEndpoint[FileUploadResponse]:
        """
        Returns a NotteEndpoint for uploading files to storage.
        """
        path = FileStorageClient.STORAGE_UPLOAD
        return NotteEndpoint(path=path, response=FileUploadResponse, method="POST")

    @staticmethod
    def _storage_upload_list_endpoint() -> NotteEndpoint[ListFilesResponse]:
        """
        Returns a NotteEndpoint for listing upload files from storage.
        """
        path = FileStorageClient.STORAGE_UPLOAD_LIST
        return NotteEndpoint(path=path, response=ListFilesResponse, method="GET")

    @staticmethod
    def _storage_download_endpoint(session_id: str | None = None) -> NotteEndpoint[FileLinkResponse]:
        """
        Returns a NotteEndpoint for getting a file link for download from storage.
        """
        path = FileStorageClient.STORAGE_DOWNLOAD
        if session_id is not None:
            path = path.format(session_id=session_id)
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

    @staticmethod
    def _storage_download_fallback_endpoint() -> NotteEndpoint[FileLinkResponse]:
        """
        Returns a NotteEndpoint for getting a file link for download from storage.
        """
        path = FileStorageClient.STORAGE_DOWNLOAD_FB
        return NotteEndpoint(path=path, response=FileLinkResponse, method="GET")

    @staticmethod
    def _storage_download_list_fallback_endpoint() -> NotteEndpoint[ListFilesResponse]:
        """
        Returns a NotteEndpoint for listing download files from storage.
        """
        path = FileStorageClient.STORAGE_DOWNLOAD_LIST_FB
        return NotteEndpoint(path=path, response=ListFilesResponse, method="GET")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        return [
            FileStorageClient._storage_upload_endpoint(),
            FileStorageClient._storage_download_endpoint(),
            FileStorageClient._storage_download_fallback_endpoint(),
            FileStorageClient._storage_upload_list_endpoint(),
            FileStorageClient._storage_download_list_endpoint(),
            FileStorageClient._storage_download_list_fallback_endpoint(),
        ]

    def upload(self, file_path: str) -> FileUploadResponse:
        """
        Upload a file to storage.
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(
                f"Cannot upload file {file_path} because it does not exist in the local file system."
            )

        endpoint = self._storage_upload_endpoint()
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

        file_path = f"{str(Path(local_dir))}/{file_name}"

        if Path(file_path).exists() and not force:
            raise ValueError(f"A file with name '{file_name}' is already at the path! Use force=True to overwrite.")

        endpoint = self._storage_download_endpoint(session_id=self.session_id)
        param_dict = {"filename": file_name}
        params = DownloadFileRequest.model_validate(param_dict)
        try:
            resp: FileLinkResponse = self.request(endpoint.with_params(params))
        except NotteAPIError:
            endpoint = self._storage_download_fallback_endpoint()
            param_dict["session_id"] = self.session_id
            params = DownloadFileFallbackRequest.model_validate(param_dict)
            resp_fallback: FileLinkResponse = self.request(endpoint.with_params(params))
            return self.request_download(resp_fallback.url, file_path)
        return self.request_download(resp.url, file_path)

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

            try:
                resp_dl: ListFilesResponse = self.request(endpoint)
                return resp_dl.files
            except NotteAPIError:
                endpoint = self._storage_download_list_fallback_endpoint()
                params: DownloadsListRequest = DownloadsListRequest.model_validate({"session_id": self.session_id})
                resp_dl_fb: ListFilesResponse = self.request(endpoint.with_params(params))
                return resp_dl_fb.files
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
