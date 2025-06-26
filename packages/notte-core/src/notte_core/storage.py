import os
from abc import ABCMeta, abstractmethod
from pathlib import Path
from tempfile import TemporaryDirectory

from loguru import logger
from typing_extensions import override

from notte_core.aws import AgentS3Storage
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


class BucketStorage(BaseStorage):
    """Storage class for accessing files from S3 bucket for upload/download"""

    def __init__(self, user_id: str):
        self.tmp_upload_dir: TemporaryDirectory[str] = TemporaryDirectory()
        self.tmp_download_dir: TemporaryDirectory[str] = TemporaryDirectory()
        self.user_id: str = user_id
        self.session_id: str = "my_agent_id"  # should be set to the current session id

        super().__init__(upload_dir=self.tmp_upload_dir.name, download_dir=self.tmp_download_dir.name)

        # Connect to S3 etc.
        self.s3: AgentS3Storage = AgentS3Storage(user_id)

    def set_session(self, session_id: str):
        self.session_id = session_id

    def cleanup(self):
        self.tmp_upload_dir.cleanup()
        self.tmp_download_dir.cleanup()

    @override
    def stop(self):
        """For any clean up logic"""
        self.cleanup()

    def sanitize(self, file_name: str) -> str:
        """Makes sure a file name only contains the name and doesn't have path traversal"""
        # Is this good enough to prevent path traversal?
        return Path(file_name).name

    @override
    def get_file(self, name: str) -> str | None:
        """Downloads a file (path arg should be file name only) from S3 to the local upload_dir and returns its local path"""
        s3_path = "uploads"
        name = self.sanitize(name)
        return self.s3.get_file(s3_path, name, str(self.upload_dir))

    @override
    def set_file(self, path: str) -> bool:
        """Uploads a file from path (full path to file locally) to S3 and returns boolean for success"""
        s3_path = f"{self.session_id}/downloads"
        return self.s3.set_file(s3_path, path)

    @override
    def list_files(self) -> list[str]:
        """Returns a list of file names for files in S3 uploads. These paths will be used by get_file()."""
        files = self.s3.list_files("uploads")
        logger.info(f"Files list: {files}")
        return files
