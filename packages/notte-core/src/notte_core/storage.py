import os
from abc import ABC, abstractmethod
from pathlib import Path


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
    def get_file(self, name: str) -> str | None:
        """Returns the local path for a file"""
        pass

    @abstractmethod
    def set_file(self, path: str) -> bool:
        """Stores a file from the local path. Ex. sends a downloaded file to remote storage."""
        pass

    @abstractmethod
    def list_uploaded_files(self) -> list[str]:
        """List all files from the upload_dir"""
        pass

    @abstractmethod
    def list_downloaded_files(self) -> list[str]:
        """List all files in the download_dir"""
        pass

    def instructions(self) -> str:
        """Return LLM instructions to append to the prompt."""
        files = ", ".join(self.list_uploaded_files())

        if len(files) > 0:
            return f"(the following files are available at these paths: {files})"

        return ""
