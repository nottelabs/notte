from __future__ import annotations

import os
import tempfile
from pathlib import Path, PureWindowsPath
from typing import final

from notte_core.cache import CacheDirectory, ensure_cache_directory
from notte_core.storage import BaseStorage, FileInfo
from notte_core.telemetry import track_usage
from typing_extensions import override

from notte_sdk._generated import operations as api
from notte_sdk._generated.resources import FilesOperations
from notte_sdk._requests import wire_request
from notte_sdk.types import FileSource, SessionFile, SessionFilesPage


def _get_cache_dir() -> Path:
    configured = os.getenv("NOTTE_CACHE_DIR")
    return Path(configured) if configured else ensure_cache_directory(CacheDirectory.FILES)


NOTTE_CACHE_DIR = _get_cache_dir()


@final
class FileStorageClient(FilesOperations):
    """Client for session-owned uploads and browser downloads."""

    @track_usage("cloud.files.upload")
    def upload(self, session_id: str, file_path: str, upload_file_name: str | None = None) -> SessionFile:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Cannot upload file {file_path}: it is not a file")
        endpoint = api.upload_session_file(session_id, wire_request(None, {}))
        return self._request_upload(endpoint, {"file": (upload_file_name or path.name, path)})

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
        _ = directory.mkdir(parents=True, exist_ok=True)
        safe_name = Path(PureWindowsPath(metadata.filename).name).name
        if safe_name in {"", ".", ".."}:
            raise ValueError(f"Unsafe filename returned for file {file_id}: {metadata.filename!r}")
        destination = directory / safe_name
        if destination.exists() and not force:
            raise FileExistsError(f"{destination} already exists; pass force=True to overwrite it")
        temporary: Path | None = None
        try:
            with self._stream_bytes(api.download_session_file(session_id, file_id)) as chunks:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=directory,
                    prefix=f".{destination.name}.",
                    suffix=".part",
                    delete=False,
                ) as output:
                    temporary = Path(output.name)
                    for chunk in chunks:
                        _ = output.write(chunk)
            _ = temporary.replace(destination)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return str(destination)


class RemoteFileStorage(BaseStorage):
    def __init__(self, session_id: str | None = None, *, _client: FileStorageClient | None = None):
        if _client is None:
            raise ValueError("FileStorageClient is required")
        self.client: FileStorageClient = _client
        self._session_id: str | None = session_id
        super().__init__(upload_dir=str(NOTTE_CACHE_DIR / "uploads"), download_dir=str(NOTTE_CACHE_DIR / "downloads"))

    @property
    @override
    def is_remote(self) -> bool:
        return True

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id

    def for_session(self, session_id: str) -> RemoteFileStorage:
        """Bind this storage once, cloning it when another session already owns it."""
        if self._session_id is None:
            self._session_id = session_id
            return self
        if self._session_id == session_id:
            return self
        return RemoteFileStorage(session_id, _client=self.client)

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            raise ValueError("A session ID is required for every file operation")
        return self._session_id

    def upload(self, file_path: str, upload_file_name: str | None = None) -> SessionFile:
        return self.client.upload(self.session_id, file_path, upload_file_name)

    def list(self, source: FileSource | str | None = None, *, limit: int = 100, offset: int = 0) -> SessionFilesPage:
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
        _ = self.upload(path)
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
