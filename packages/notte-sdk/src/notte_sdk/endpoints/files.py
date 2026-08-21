from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, final

import requests
from notte_core.common.cache import CacheDirectory, ensure_cache_directory
from notte_core.common.telemetry import track_usage
from notte_core.storage import BaseStorage, FileInfo
from typing_extensions import override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import FileSource, ListFilesResponse, SessionFile

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


def _get_cache_dir() -> Path:
    configured = os.getenv("NOTTE_CACHE_DIR")
    return Path(configured) if configured else ensure_cache_directory(CacheDirectory.FILES)


NOTTE_CACHE_DIR = _get_cache_dir()


@final
class FileStorageClient(BaseClient):
    """Client for session-owned uploads and browser downloads."""

    def __init__(
        self, root_client: NotteClient, api_key: str | None = None, server_url: str | None = None, verbose: bool = False
    ):
        super().__init__(root_client, "sessions", server_url=server_url, api_key=api_key, verbose=verbose)

    @staticmethod
    def _file_endpoint(session_id: str, file_id: str | None = None) -> str:
        path = f"{session_id}/files"
        return f"{path}/{file_id}" if file_id is not None else path

    @track_usage("cloud.files.upload")
    def upload(self, session_id: str, file_path: str, upload_file_name: str | None = None) -> SessionFile:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Cannot upload file {file_path}: it is not a file")
        endpoint = NotteEndpoint(path=self._file_endpoint(session_id), response=SessionFile, method="POST")
        with path.open("rb") as payload:
            files = {"file": (upload_file_name or path.name, payload)}
            return self.request(endpoint.model_copy(update={"files": files}))

    @track_usage("cloud.files.list")
    def list(
        self,
        session_id: str,
        *,
        source: FileSource | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ListFilesResponse:
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if source is not None:
            params["source"] = source.value if isinstance(source, FileSource) else source
        endpoint = NotteEndpoint(path=self._file_endpoint(session_id), response=ListFilesResponse, method="GET")
        response = requests.get(
            self.request_path(endpoint),
            headers=self.headers(),
            params=params,
            timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        if not response.ok:
            raise NotteAPIError(path=f"sessions/{session_id}/files", response=response)
        return ListFilesResponse.model_validate(response.json())

    def metadata(self, session_id: str, file_id: str) -> SessionFile:
        offset = 0
        while True:
            page = self.list(session_id, limit=1000, offset=offset)
            match = next((item for item in page.files if item.id == file_id), None)
            if match is not None:
                return match
            offset += len(page.files)
            if offset >= page.total or not page.files:
                raise FileNotFoundError(f"File {file_id} was not found in session {session_id}")

    @track_usage("cloud.files.download")
    def download(self, session_id: str, file_id: str, local_dir: str = ".", *, force: bool = False) -> str:
        metadata = self.metadata(session_id, file_id)
        directory = Path(local_dir)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / metadata.filename
        if destination.exists() and not force:
            raise FileExistsError(f"{destination} already exists; pass force=True to overwrite it")
        endpoint = NotteEndpoint(path=self._file_endpoint(session_id, file_id), response=SessionFile, method="GET")
        response = requests.get(
            self.request_path(endpoint),
            headers=self.headers(),
            timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
            stream=True,
        )
        if not response.ok:
            raise NotteAPIError(path=f"sessions/{session_id}/files/{file_id}", response=response)
        temporary = destination.with_name(f".{destination.name}.part")
        try:
            with temporary.open("wb") as output:
                for chunk in response.iter_content(self.DEFAULT_FILE_CHUNK_SIZE):
                    if chunk:
                        output.write(chunk)
            temporary.replace(destination)
        finally:
            response.close()
            temporary.unlink(missing_ok=True)
        return str(destination)

    @track_usage("cloud.files.delete")
    def delete(self, session_id: str, file_id: str) -> None:
        endpoint = NotteEndpoint(path=self._file_endpoint(session_id, file_id), response=SessionFile, method="DELETE")
        response = requests.delete(
            self.request_path(endpoint), headers=self.headers(), timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS
        )
        if not response.ok:
            raise NotteAPIError(path=f"sessions/{session_id}/files/{file_id}", response=response)


class RemoteFileStorage(BaseStorage):
    def __init__(self, session_id: str | None = None, *, _client: FileStorageClient | None = None):
        if _client is None:
            raise ValueError("FileStorageClient is required")
        self.client = _client
        self._session_id = session_id
        super().__init__(upload_dir=str(NOTTE_CACHE_DIR / "uploads"), download_dir=str(NOTTE_CACHE_DIR / "downloads"))

    @property
    @override
    def is_remote(self) -> bool:
        return True

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            raise ValueError("A session ID is required for every file operation")
        return self._session_id

    def upload(self, file_path: str, upload_file_name: str | None = None) -> SessionFile:
        return self.client.upload(self.session_id, file_path, upload_file_name)

    def list(self, source: FileSource | str | None = None, *, limit: int = 100, offset: int = 0) -> ListFilesResponse:
        return self.client.list(self.session_id, source=source, limit=limit, offset=offset)

    def download(self, file_id: str, local_dir: str = ".", *, force: bool = False) -> str:
        return self.client.download(self.session_id, file_id, local_dir, force=force)

    def delete(self, file_id: str) -> None:
        self.client.delete(self.session_id, file_id)

    @override
    async def get_file(self, name: str) -> str | None:
        assert self.upload_dir is not None
        match = next(
            (file for file in self.list(FileSource.USER_UPLOAD, limit=1000).files if file.filename == name), None
        )
        return None if match is None else self.download(match.id, self.upload_dir, force=True)

    @override
    async def set_file(self, path: str) -> bool:
        self.upload(path)
        return True

    @staticmethod
    def _file_info(file: SessionFile) -> FileInfo:
        return FileInfo(
            name=file.filename, size=file.size, file_ext=Path(file.filename).suffix, updated_at=file.created_at
        )

    @override
    async def alist_uploaded_files(self) -> list[FileInfo]:
        return [self._file_info(file) for file in self.list(FileSource.USER_UPLOAD, limit=1000).files]

    @override
    async def alist_downloaded_files(self) -> list[FileInfo]:
        return [self._file_info(file) for file in self.list(FileSource.SESSION_DOWNLOAD, limit=1000).files]
