from __future__ import annotations

import asyncio
import os
import tempfile
from abc import ABC
from pathlib import Path, PureWindowsPath
from typing import IO, ClassVar, Generic, TypeVar, final

from notte_core.cache import CacheDirectory, ensure_cache_directory
from notte_core.storage import BaseStorage, FileInfo
from notte_core.telemetry import track_usage
from typing_extensions import override

from notte_sdk._generated import operations as api
from notte_sdk._generated.resources import AsyncFilesOperations, FilesOperations
from notte_sdk._requests import wire_request
from notte_sdk._transport import athread_finally, athread_owned, awrite_chunks
from notte_sdk.endpoints.base import NotteEndpoint, UploadFile
from notte_sdk.types import FileSource, SessionFile, SessionFilesPage


def _get_cache_dir() -> Path:
    configured = os.getenv("NOTTE_CACHE_DIR")
    return Path(configured) if configured else ensure_cache_directory(CacheDirectory.FILES)


NOTTE_CACHE_DIR = _get_cache_dir()


def _upload_request(
    session_id: str, file_path: str, upload_file_name: str | None
) -> tuple[NotteEndpoint[SessionFile], dict[str, UploadFile]]:
    """The endpoint and the file of `upload`; raises when `file_path` is not a file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Cannot upload file {file_path}: it is not a file")
    endpoint = api.upload_session_file(session_id, wire_request(None, {}))
    return endpoint, {"file": (upload_file_name or path.name, path)}


def _find_file(page: SessionFilesPage, session_id: str, file_id: str, offset: int) -> SessionFile | int:
    """The file when `page` has it, else the offset of the next page; raises after the last page."""
    match = next((item for item in page.files if item.id == file_id), None)
    if match is not None:
        return match
    offset += len(page.files)
    if offset >= page.total or not page.files:
        raise FileNotFoundError(f"File {file_id} was not found in session {session_id}")
    return offset


def _download_destination(metadata: SessionFile, file_id: str, local_dir: str, force: bool) -> Path:
    """Where `download` writes a file: its safe name in `local_dir`, which is created if needed."""
    directory = Path(local_dir)
    _ = directory.mkdir(parents=True, exist_ok=True)
    safe_name = Path(PureWindowsPath(metadata.filename).name).name
    if safe_name in {"", ".", ".."}:
        raise ValueError(f"Unsafe filename returned for file {file_id}: {metadata.filename!r}")
    destination = directory / safe_name
    if destination.exists() and not force:
        raise FileExistsError(f"{destination} already exists; pass force=True to overwrite it")
    return destination


def _partial_file(destination: Path) -> IO[bytes]:
    """The temporary file a download is written to, next to its destination."""
    return tempfile.NamedTemporaryFile(
        mode="wb",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".part",
        delete=False,
    )


def _discard_partial(output: IO[bytes]) -> None:
    output.close()
    Path(output.name).unlink(missing_ok=True)


@final
class FileStorageClient(FilesOperations):
    """Client for session-owned uploads and browser downloads."""

    @track_usage("cloud.files.upload")
    def upload(self, session_id: str, file_path: str, upload_file_name: str | None = None) -> SessionFile:
        return self._request_upload(*_upload_request(session_id, file_path, upload_file_name))

    def metadata(self, session_id: str, file_id: str) -> SessionFile:
        offset = 0
        while True:
            found = _find_file(self.list(session_id, limit=1000, offset=offset), session_id, file_id, offset)
            if isinstance(found, SessionFile):
                return found
            offset = found

    @track_usage("cloud.files.download")
    def download(self, session_id: str, file_id: str, local_dir: str = ".", *, force: bool = False) -> str:
        metadata = self.metadata(session_id, file_id)
        destination = _download_destination(metadata, file_id, local_dir, force)
        temporary: Path | None = None
        try:
            with self._stream_bytes(api.download_session_file(session_id, file_id)) as chunks:
                with _partial_file(destination) as output:
                    temporary = Path(output.name)
                    for chunk in chunks:
                        _ = output.write(chunk)
            _ = temporary.replace(destination)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return str(destination)


@final
class AsyncFileStorageClient(AsyncFilesOperations):
    """The async twin of `FileStorageClient`, for `AsyncNotteClient`. Local files are read and
    written in worker threads; an uploaded file is read whole before it is sent."""

    @track_usage("cloud.files.upload")
    async def upload(self, session_id: str, file_path: str, upload_file_name: str | None = None) -> SessionFile:
        endpoint, files = await asyncio.to_thread(_upload_request, session_id, file_path, upload_file_name)
        return await self._request_upload(endpoint, files)

    async def metadata(self, session_id: str, file_id: str) -> SessionFile:
        offset = 0
        while True:
            found = _find_file(await self.list(session_id, limit=1000, offset=offset), session_id, file_id, offset)
            if isinstance(found, SessionFile):
                return found
            offset = found

    @track_usage("cloud.files.download")
    async def download(self, session_id: str, file_id: str, local_dir: str = ".", *, force: bool = False) -> str:
        metadata = await self.metadata(session_id, file_id)
        destination = await asyncio.to_thread(_download_destination, metadata, file_id, local_dir, force)
        temporary: Path | None = None
        try:
            async with self._stream_bytes(api.download_session_file(session_id, file_id)) as chunks:
                # A cancellation while the file is created still removes it.
                output = await athread_owned(_discard_partial, _partial_file, destination)
                temporary = Path(output.name)
                try:
                    await awrite_chunks(chunks, output)
                finally:
                    await athread_finally(output.close)
            _ = await asyncio.to_thread(temporary.replace, destination)
            temporary = None
        finally:
            if temporary is not None:
                await athread_finally(temporary.unlink, missing_ok=True)
        return str(destination)


TFiles = TypeVar("TFiles", FileStorageClient, AsyncFileStorageClient)


# What `RemoteFileStorage` and `AsyncRemoteFileStorage` share: the session binding, without I/O.
# No docstring, so the public classes keep `BaseStorage`'s in the SDK reference.
class _SessionStorage(BaseStorage, ABC, Generic[TFiles]):
    _CLIENT: ClassVar[str] = "FileStorageClient"

    def __init__(self, session_id: str | None = None, *, _client: TFiles | None = None):
        if _client is None:
            raise ValueError(f"{self._CLIENT} is required")
        self.client: TFiles = _client
        self._session_id: str | None = session_id
        super().__init__(upload_dir=str(NOTTE_CACHE_DIR / "uploads"), download_dir=str(NOTTE_CACHE_DIR / "downloads"))

    @property
    @override
    def is_remote(self) -> bool:
        return True

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id

    def _bind(self, session_id: str) -> bool:
        """Bind this storage to `session_id` unless another session owns it; whether it is bound to it."""
        if self._session_id is None:
            self._session_id = session_id
            return True
        return self._session_id == session_id

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            raise ValueError("A session ID is required for every file operation")
        return self._session_id

    @staticmethod
    def _named(page: SessionFilesPage, name: str) -> SessionFile | None:
        return next((file for file in page.files if file.filename == name), None)

    @staticmethod
    def _file_info(file: SessionFile) -> FileInfo:
        return FileInfo(
            name=file.filename, size=file.size, file_ext=Path(file.filename).suffix, updated_at=file.created_at
        )


class RemoteFileStorage(_SessionStorage[FileStorageClient]):
    def for_session(self, session_id: str) -> RemoteFileStorage:
        """Bind this storage once, cloning it when another session already owns it."""
        return self if self._bind(session_id) else RemoteFileStorage(session_id, _client=self.client)

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
        match = self._named(self.list(FileSource.USER_UPLOAD, limit=1000), name)
        return None if match is None else self.download(match.id, self.upload_dir, force=True)

    @override
    async def set_file(self, path: str) -> bool:
        _ = self.upload(path)
        return True

    @override
    async def alist_uploaded_files(self) -> list[FileInfo]:
        return [self._file_info(file) for file in self.list(FileSource.USER_UPLOAD, limit=1000).files]

    @override
    async def alist_downloaded_files(self) -> list[FileInfo]:
        return [self._file_info(file) for file in self.list(FileSource.SESSION_DOWNLOAD, limit=1000).files]


class AsyncRemoteFileStorage(_SessionStorage[AsyncFileStorageClient]):
    """The async twin of `RemoteFileStorage`, from `AsyncNotteClient.FileStorage`.

    `upload`, `list`, `download` and `delete` are coroutines. `BaseStorage`'s sync
    `list_uploaded_files` and `list_downloaded_files` start their own event loop, which this
    storage's client cannot use: await `alist_uploaded_files` and `alist_downloaded_files` instead.
    """

    _CLIENT: ClassVar[str] = "AsyncFileStorageClient"

    def for_session(self, session_id: str) -> AsyncRemoteFileStorage:
        """Bind this storage once, cloning it when another session already owns it."""
        return self if self._bind(session_id) else AsyncRemoteFileStorage(session_id, _client=self.client)

    async def upload(self, file_path: str, upload_file_name: str | None = None) -> SessionFile:
        return await self.client.upload(self.session_id, file_path, upload_file_name)

    async def list(
        self, source: FileSource | str | None = None, *, limit: int = 100, offset: int = 0
    ) -> SessionFilesPage:
        return await self.client.list(self.session_id, source=source, limit=limit, offset=offset)

    async def download(self, file_id: str, local_dir: str = ".", *, force: bool = False) -> str:
        return await self.client.download(self.session_id, file_id, local_dir, force=force)

    async def delete(self, file_id: str) -> None:
        await self.client.delete(self.session_id, file_id)

    @override
    async def get_file(self, name: str) -> str | None:
        assert self.upload_dir is not None
        match = self._named(await self.list(FileSource.USER_UPLOAD, limit=1000), name)
        return None if match is None else await self.download(match.id, self.upload_dir, force=True)

    @override
    async def set_file(self, path: str) -> bool:
        _ = await self.upload(path)
        return True

    @override
    async def alist_uploaded_files(self) -> list[FileInfo]:
        return [self._file_info(file) for file in (await self.list(FileSource.USER_UPLOAD, limit=1000)).files]

    @override
    async def alist_downloaded_files(self) -> list[FileInfo]:
        return [self._file_info(file) for file in (await self.list(FileSource.SESSION_DOWNLOAD, limit=1000)).files]
