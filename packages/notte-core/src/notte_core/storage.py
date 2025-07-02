import os
from abc import ABCMeta, abstractmethod
from pathlib import Path

from typing_extensions import override

from notte_core.common.resource import SyncResource


class BaseStorage(SyncResource, metaclass=ABCMeta):
    """Base class for storage implementations that handle upload and download file storage and retrieval."""

    def __init__(self, upload_dir: str | None = None, download_dir: str | None = None):
        self.upload_dir: Path | None = None
        self.download_dir: str | None = None

        if upload_dir is not None:
            self.upload_dir = Path(upload_dir)

        if download_dir is not None:
            self.download_dir = f"{str(Path(download_dir))}{os.sep}"

    @override
    def start(self) -> None:
        """For any setup logic"""
        pass

    @override
    def stop(self) -> None:
        """For any clean up logic"""
        pass

    @abstractmethod
    def get_file(self, name: str) -> str | None:
        """Returns the local path for a file"""
        pass

    @abstractmethod
    def set_file(self, path: str) -> bool:
        """Stores a file from the local path. Ex. sends a downloaded file to S3."""
        pass

    @abstractmethod
    def list_files(self) -> list[str]:
        """List all files from the upload_dir"""
        pass

    @abstractmethod
    def list_downloaded_files(self) -> list[str]:
        """List all files in the download_dir"""
        pass

    def instructions(self) -> str:
        """Return LLM instructions to append to the prompt."""
        files = ", ".join(self.list_files())

        if len(files) > 0:
            return f"(the following files are available at these paths: {files})"
        else:
            return ""


class LocalStorage(BaseStorage):
    """Storage class for using local directories for file upload/download"""

    @override
    def get_file(self, name: str) -> str | None:
        if not Path(name).exists():
            # raise FileNotFoundError(f"File {name} does not exist")
            return None

        return name

    @override
    def set_file(self, path: str) -> bool:
        return True

    @override
    def list_files(self) -> list[str]:
        """List all files from the local upload_dir."""
        if self.upload_dir is None:
            return []

        all_files = [
            str(p)
            for p in self.upload_dir.rglob("*")
            if p.is_file()
            and not p.name.startswith(".")
            and not any(part.startswith(".") for part in p.parts[len(self.upload_dir.parts) :])
        ]

        # [os.path.join(self.upload_dir, f) for f in os.listdir(self.upload_dir) if os.path.isfile(os.path.join(self.upload_dir, f))]

        return all_files

    @override
    def list_downloaded_files(self) -> list[str]:
        if self.download_dir is None:
            return []

        download_path = Path(self.download_dir)

        all_files = [
            str(p)
            for p in download_path.rglob("*")
            if p.is_file()
            and not p.name.startswith(".")
            and not any(part.startswith(".") for part in p.parts[len(download_path.parts) :])
        ]

        # [os.path.join(self.upload_dir, f) for f in os.listdir(self.upload_dir) if os.path.isfile(os.path.join(self.upload_dir, f))]

        return all_files
