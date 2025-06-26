import os
from pathlib import Path
from typing import Any, BinaryIO, ClassVar, Protocol, final

import boto3


class S33Interface(Protocol):
    # def __init__(self, tool: str, bucket_name: str, aws_access_key_id: str, aws_secret_access_key: str, region_name: str, endpoint_url: str | None = None): ...

    def upload_file(self, Filename: str, Bucket: str, Key: str) -> bool: ...

    def upload_fileobj(self, Fileobj: BinaryIO | Path | bytes, Bucket: str, Key: str) -> bool: ...

    def download_file(self, Filename: str, Bucket: str, Key: str) -> bool: ...

    def list_objects_v2(self, Bucket: str, Prefix: str) -> dict[str, Any]: ...

    def get_object(self, Bucket: str, Key: str) -> bytes | None: ...

    def list_files(self) -> list[str]: ...

    def generate_presigned_url(self, ClientMethod: str, Params: dict[str, Any], ExpiresIn: int) -> str: ...


@final
class AgentS3Storage:
    notte_domain: ClassVar[str] = "files.notte.cc"

    def __init__(self, user_id: str):
        """
        Initialize S3 storage client.

        Args:
            user_id: The ID of the user
            session_id: The ID of the session
            endpoint_url: Custom endpoint URL (for MinIO or other S3-compatible services)
            custom_domain: Custom domain for the S3 bucket (e.g. files.notte.cc)
        """

        # get bucket creds/details from API call with user_id?

        self.s3: S33Interface = boto3.client(  # pyright: ignore [reportUnknownMemberType]
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION"),
        )
        # endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
        self.bucket_name = "notte-agents-files"  # set based on user_id?
        self.base_dir = f"{user_id}"

    def _get_object_key(self, path: str, file_name: Path | str) -> str:
        """
        Get the S3 object key for a specific user and agent.
        This is an internal function that should not be exposed to agents.

        Args:
            path: s3 path relative to base_dir where obj is stored
            file_name: name of the file only
        """
        name = file_name.name if isinstance(file_name, Path) else file_name
        dir_path = f"{str(Path(path))}"
        return f"{self.base_dir}/{dir_path}/{name}"

    def set_file(self, file_path: str, local_file: str) -> bool:
        """
        Upload a file to S3.

        Args:
            file_path: Path of file in S3 relative to base_dir
            local_file: Local path to file

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            file = Path(local_file)
            if not file.exists():
                raise FileNotFoundError(f"File {file} does not exist")

            object_key = self._get_object_key(file_path, file.name)
            _ = self.s3.upload_file(Filename=str(file), Bucket=self.bucket_name, Key=object_key)

            return True
        except Exception:
            return False

    def get_file(self, file_path: str, file_name: str, upload_dir: str) -> str | None:
        """Downloads a file from s3 base_dir/file_path/file_name to local upload_dir/file_name"""
        try:
            local_path = f"{str(Path(upload_dir))}/{file_name}"
            object_key = self._get_object_key(file_path, file_name)
            _ = self.s3.download_file(Bucket=self.bucket_name, Key=object_key, Filename=local_path)
            return local_path
        except Exception:
            return None

    def list_files(self, path: str) -> list[str]:
        """
        List all files for a specific user and agent in S3.
        Returns:
            list[str]: List of file names in the directory
        """
        try:
            prefix = f"{self.base_dir}/{path}/"
            response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)

            files: list[str] = []
            for obj in response.get("Contents", []):
                # Remove the prefix to get just the filename
                key = obj["Key"]
                if key != prefix:  # Skip the directory marker
                    files.append(key.replace(prefix, ""))

            return files
        except Exception:
            return []

    def get_presigned_url(
        self, file_path: str, file_name: str, expires_in: int = 3600, operation: str = "get_object"
    ) -> str:
        """
        Generate a presigned URL for file operations.
        If use_website_hosting is True, returns a direct website hosting URL instead.

        Args:
            file_name: Name of the file
            expires_in: URL expiration time in seconds (ignored if use_website_hosting is True)
            operation: S3 operation ('get_object' or 'put_object')

        Returns:
            str: URL to access the file
        """
        object_key = self._get_object_key(file_path, file_name)
        url = self.s3.generate_presigned_url(
            ClientMethod=operation, Params={"Bucket": self.bucket_name, "Key": object_key}, ExpiresIn=expires_in
        )
        s3_domain: str = f"{self.bucket_name}.s3.amazonaws.com"
        return url.replace(s3_domain, self.notte_domain)
