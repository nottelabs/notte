import asyncio
import datetime as dt
import os
import warnings
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, model_validator


class FileInfo(BaseModel):
    """File metadata for file listings."""

    name: str
    size: int
    file_ext: str
    updated_at: dt.datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_file_info(cls, data: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(data, str):
            warnings.warn("Passing a string to FileInfo is deprecated. Pass a dict[str, Any] instead.")
            data = {"name": data, "file_ext": data.split(".")[-1], "size": 0, "updated_at": None}
        return data


class BaseStorage(ABC):
    """Base class for storage implementations that handle upload and download file storage and retrieval."""

    def __init__(self, upload_dir: str | None = None, download_dir: str | None = None):
        self.upload_dir: str | None = None
        self.download_dir: str | None = None

        if upload_dir is not None:
            self.upload_dir = str(Path(upload_dir))

        if download_dir is not None:
            self.download_dir = f"{str(Path(download_dir))}{os.sep}"

    @abstractmethod
    async def get_file(self, name: str) -> str | None:
        """Returns the local path for a file"""
        pass

    @abstractmethod
    async def set_file(self, path: str) -> bool:
        """Stores a file from the local path. Ex. sends a downloaded file to remote storage."""
        pass

    @abstractmethod
    async def alist_uploaded_files(self) -> list[FileInfo]:
        """List all files from the upload_dir"""
        pass

    @abstractmethod
    async def alist_downloaded_files(self) -> list[FileInfo]:
        """List all files in the download_dir"""
        pass

    def list_uploaded_files(self) -> list[FileInfo]:
        """List all files from the upload_dir"""
        return asyncio.run(self.alist_uploaded_files())

    def list_downloaded_files(self) -> list[FileInfo]:
        """List all files in the download_dir"""
        return asyncio.run(self.alist_downloaded_files())

    async def instructions(self) -> str:
        """Return LLM instructions to append to the prompt."""
        file_infos = await self.alist_uploaded_files()
        files = ", ".join(f.name for f in file_infos)

        if len(files) > 0:
            return f"(the following files are available at these paths: {files})"

        return ""
