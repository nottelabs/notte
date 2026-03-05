"""Async base client for the Notte SDK."""
# pyright: reportImportCycles=false, reportRedeclaration=false, reportArgumentType=false, reportUnknownVariableType=false

from __future__ import annotations

import json
import os
import re
from abc import ABC
from collections.abc import Sequence
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, Self, TypeVar

import httpx
from notte_core import __version__ as notte_core_version
from notte_core.common.logging import logger
from pydantic import BaseModel, ValidationError

from notte_sdk._async.http import AsyncHTTPClient
from notte_sdk.errors import NotteAPIError, NotteAPIExecutionError

if TYPE_CHECKING:
    from notte_sdk._async.client import AsyncNotteClient

TResponse = TypeVar("TResponse", bound=BaseModel, covariant=True)

# Global variable to cache PyPI version check result
_cached_pypi_version: str | None = None
_version_check_performed: bool = False


class NotteEndpoint(BaseModel, Generic[TResponse]):
    """Endpoint configuration for API requests."""

    path: str
    response: type[TResponse]
    request: BaseModel | None = None
    method: Literal["GET", "POST", "DELETE", "PATCH"]
    params: BaseModel | None = None
    files: dict[str, Any] | None = None

    def with_request(self, request: BaseModel) -> Self:
        """Return a deep copy of the endpoint with the specified request."""
        return self.model_copy(update={"request": request})

    def with_params(self, params: BaseModel) -> Self:
        """Return a new endpoint instance with updated parameters."""
        return self.model_copy(update={"params": params})

    def with_file(self, file_path: str) -> Self:
        """Return a new endpoint instance with a file object."""
        if not os.path.exists(file_path):
            raise ValueError("The file doesn't exist!")

        file_dict: dict[str, Any] = {"file": open(file_path, "rb")}
        return self.model_copy(update={"files": file_dict})


class AsyncBaseClient(ABC):
    """Base class for async API clients."""

    DEFAULT_NOTTE_API_URL: ClassVar[str] = "https://api.notte.cc"
    DEFAULT_REQUEST_TIMEOUT_SECONDS: ClassVar[int] = 60
    DEFAULT_FILE_CHUNK_SIZE: ClassVar[int] = 8192

    HEALTH_CHECK_ENDPOINT: ClassVar[str] = "health"

    def __init__(
        self,
        root_client: "AsyncNotteClient",
        base_endpoint_path: str | None,
        http_client: AsyncHTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize a new async API client instance.

        Args:
            root_client: The root AsyncNotteClient instance.
            base_endpoint_path: Optional base path to be prefixed to endpoint URLs.
            http_client: The shared AsyncHTTPClient instance.
            server_url: The API server URL.
            api_key: The API key for authentication.
            verbose: Whether to enable verbose logging.
        """
        self.root_client: "AsyncNotteClient" = root_client
        self._http: AsyncHTTPClient = http_client
        self.token: str = api_key
        self.server_url: str = server_url
        self.base_endpoint_path: str | None = base_endpoint_path
        self.verbose: bool = verbose

        # Check for version mismatch and warn user if needed
        self.check_and_warn_version_mismatch()

    def is_custom_endpoint_available(self) -> bool:
        """Check if the custom endpoint is available."""
        if "localhost" in self.server_url:
            return True
        return self.server_url != self.DEFAULT_NOTTE_API_URL

    def _get_latest_pypi_version(self, package_name: str = "notte-sdk") -> str:
        """Get the latest version of a package from PyPI.

        This is a private method used internally for version checking.
        Uses synchronous requests since this is only called once at startup.
        """
        import requests

        try:
            headers = {"User-Agent": f"notte-sdk/{notte_core_version} (https://github.com/NotteAI/notte)"}

            response = requests.get(
                f"https://pypi.org/pypi/{package_name}/json",
                headers=headers,
                timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

            data = response.json()
            return data["info"]["version"]

        except requests.RequestException as e:
            logger.debug(f"Failed to fetch PyPI information for {package_name}: {e}")
            raise
        except KeyError as e:
            logger.debug(f"Unexpected PyPI API response format for {package_name}: {e}")
            raise

    def check_and_warn_version_mismatch(self) -> None:
        """Check if the current notte-sdk version matches the latest PyPI version."""
        global _cached_pypi_version, _version_check_performed

        # Only check once per process
        if _version_check_performed:
            return

        _version_check_performed = True

        # Skip version check for development versions
        if ".dev" in notte_core_version:
            return

        try:
            latest_version = self._get_latest_pypi_version("notte-sdk")
            _cached_pypi_version = latest_version

            if self._is_version_older(notte_core_version, latest_version):
                logger.warning(
                    f"You are using notte-sdk version {notte_core_version}, but version {latest_version} is available on PyPI. Run 'pip install notte-sdk=={latest_version}' to avoid any interruptions."
                )

        except Exception:
            pass

    def _is_version_older(self, current_version: str, latest_version: str) -> bool:
        """Check if the current version is older than the latest version."""
        try:
            current_parts = [int(x) for x in current_version.split(".")]
            latest_parts = [int(x) for x in latest_version.split(".")]

            max_len = max(len(current_parts), len(latest_parts))
            current_parts.extend([0] * (max_len - len(current_parts)))
            latest_parts.extend([0] * (max_len - len(latest_parts)))

            return current_parts < latest_parts
        except (ValueError, AttributeError):
            return False

    def _should_suggest_upgrade(self) -> tuple[bool, str | None]:
        """Check if we should suggest an upgrade based on version comparison."""
        global _cached_pypi_version

        if _cached_pypi_version is None:
            return False, None

        if ".dev" in notte_core_version:
            return False, _cached_pypi_version

        should_suggest = self._is_version_older(notte_core_version, _cached_pypi_version)
        return should_suggest, _cached_pypi_version

    def _create_upgrade_error_message(
        self, error_context: str, cached_version: str, original_error: str | None = None
    ) -> str:
        """Create a standardized upgrade suggestion error message."""
        base_message = (
            f"{error_context}. This might be due to API schema changes. "
            f"Current SDK version: {notte_core_version}, Latest available: {cached_version}. "
            f"Either you made a mistake in the request arguments, or you should upgrade to the latest "
            f"notte-sdk version by running: 'pip install notte-sdk=={cached_version}'"
        )

        if original_error:
            base_message += f". Original error: {original_error}"

        return base_message

    async def health_check(self) -> None:
        """Health check the Notte API."""
        try:
            response = await self._http.get(f"/{self.HEALTH_CHECK_ENDPOINT}")
            if response.status_code != 200:
                logger.error(f"Health check failed with status code {response.status_code}.")
                raise Exception(
                    f"Health check failed with status code {response.status_code}. Please check your server URL."
                )
        except httpx.ConnectError as e:
            logger.error(f"Health check failed with error: {e}. Please check your server URL.")
            raise Exception(
                "Health check failed because the server is not reachable. Please check your server URL."
            ) from e
        logger.info("Health check passed. API ready to serve requests.")

    def request_path(self, endpoint: NotteEndpoint[TResponse]) -> str:
        """Constructs the full request path for the given API endpoint."""
        # check that not "/{XYZ}" are in the path to avoid missing formatted paths
        unformatted_path = re.match(r"/\{\w+\}", endpoint.path)
        if unformatted_path:
            raise ValueError(f"Endpoint path cannot contain '{unformatted_path.group(0)}' (path={endpoint.path})")

        path = ""

        # Add base endpoint path if it exists
        if self.base_endpoint_path is not None:
            base_path = self.base_endpoint_path.strip("/")
            if base_path:
                path = "/" + base_path

        # Add the endpoint path
        endpoint_path = endpoint.path.lstrip("/")
        if endpoint_path:
            path = path + "/" + endpoint_path

        return path

    async def _request(
        self, endpoint: NotteEndpoint[TResponse], headers: dict[str, str] | None = None, timeout: int | None = None
    ) -> dict[str, Any]:
        """Execute an HTTP request for the given API endpoint."""
        path = self.request_path(endpoint)
        params = endpoint.params.model_dump(exclude_none=True) if endpoint.params is not None else None
        files = endpoint.files if endpoint.files is not None else None

        if self.verbose:
            logger.info(f"Making `{endpoint.method}` request to `{path}` with params `{params}`.")

        request_headers = headers or {}

        match endpoint.method:
            case "GET":
                response = await self._http.get(
                    path,
                    headers=request_headers,
                    params=params,
                    timeout=timeout or self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
                )
            case "POST" | "PATCH":
                if endpoint.request is None and endpoint.files is None:
                    raise ValueError("Request model or file is required for POST requests")

                json_data = None
                data = None

                if endpoint.request is not None:
                    if files is None:
                        json_data = endpoint.request.model_dump(exclude_none=True)
                    else:
                        data = endpoint.request.model_dump(exclude_none=True)

                response = await self._http.request(
                    endpoint.method,
                    path,
                    headers=request_headers,
                    params=params,
                    json=json_data,
                    data=data,
                    files=files,
                    timeout=timeout or self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
                )
            case "DELETE":
                response = await self._http.delete(
                    path,
                    headers=request_headers,
                    params=params,
                    timeout=timeout or self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
                )

        if response.status_code != 200:
            # Check for 422 status code with Pydantic validation errors first
            if response.status_code == 422:
                should_upgrade, cached_version = self._should_suggest_upgrade()
                if should_upgrade and cached_version:
                    try:
                        error_data = response.json()
                        error_message = error_data.get("message", "")

                        if (
                            "extra_forbidden" in error_message
                            or "Extra inputs are not permitted" in error_message
                            or "'type':" in error_message
                        ):
                            upgrade_msg = self._create_upgrade_error_message(
                                "API returned 422 validation error", cached_version, error_message
                            )
                            raise RuntimeError(upgrade_msg)
                    except (JSONDecodeError, KeyError):
                        pass

            # Create a mock response object for error handling
            class MockResponse:
                def __init__(self, httpx_resp: httpx.Response):
                    self.status_code: int = httpx_resp.status_code
                    self.text: str = httpx_resp.text
                    self.headers: dict[str, str] = dict(httpx_resp.headers)

                def json(self) -> Any:
                    return json.loads(self.text)

            mock_resp = MockResponse(response)

            if response.headers.get("x-error-class") == "NotteApiExecutionError":
                raise NotteAPIExecutionError(path=f"{self.base_endpoint_path}/{endpoint.path}", response=mock_resp)

            raise NotteAPIError(path=f"{self.base_endpoint_path}/{endpoint.path}", response=mock_resp)

        response_dict: Any = response.json()
        if "detail" in response_dict:

            class MockResponse:
                def __init__(self, httpx_resp: httpx.Response, data: Any):
                    self.status_code: int = httpx_resp.status_code
                    self.text: str = httpx_resp.text
                    self._data: Any = data

                def json(self) -> Any:
                    return self._data

            raise NotteAPIError(
                path=f"{self.base_endpoint_path}/{endpoint.path}", response=MockResponse(response, response_dict)
            )

        return response_dict

    async def request(
        self, endpoint: NotteEndpoint[TResponse], headers: dict[str, str] | None = None, timeout: int | None = None
    ) -> TResponse:
        """Request the specified API endpoint and return the validated response."""
        response: Any = await self._request(endpoint, headers=headers, timeout=timeout)
        if not isinstance(response, dict):

            class MockResponse:
                def __init__(self, data: Any):
                    self.status_code: int = 200
                    self._data: Any = data

                def json(self) -> Any:
                    return self._data

            raise NotteAPIError(path=f"{self.base_endpoint_path}/{endpoint.path}", response=MockResponse(response))

        try:
            return endpoint.response.model_validate(response)
        except ValidationError as e:
            should_upgrade, cached_version = self._should_suggest_upgrade()

            if should_upgrade and cached_version:
                upgrade_msg = self._create_upgrade_error_message("Pydantic validation failed", cached_version)
                raise RuntimeError(upgrade_msg) from e
            else:
                raise

    async def request_list(self, endpoint: NotteEndpoint[TResponse]) -> Sequence[TResponse]:
        """Retrieve and validate a list of responses from the API."""
        response_list: Any = await self._request(endpoint)
        if not isinstance(response_list, list):
            if "items" in response_list:
                response_list = response_list["items"]
            if not isinstance(response_list, list):

                class MockResponse:
                    def __init__(self, data: Any):
                        self.status_code: int = 200
                        self._data: Any = data

                    def json(self) -> Any:
                        return self._data

                raise NotteAPIError(
                    path=f"{self.base_endpoint_path}/{endpoint.path}", response=MockResponse(response_list)
                )

        try:
            return [endpoint.response.model_validate(item) for item in response_list]
        except ValidationError as e:
            should_upgrade, cached_version = self._should_suggest_upgrade()

            if should_upgrade and cached_version:
                upgrade_msg = self._create_upgrade_error_message(
                    "Pydantic validation failed for list response", cached_version
                )
                raise RuntimeError(upgrade_msg) from e
            else:
                raise

    async def _request_file(
        self, endpoint: NotteEndpoint[TResponse], file_type: str, output_file: str | None = None
    ) -> bytes:
        """Request a file from the API."""
        path = self.request_path(endpoint)
        response = await self._http.get(path)

        try:
            response_dict: Any = response.json()
            if "detail" in response_dict:
                raise ValueError(response_dict["detail"])
            raise ValueError(f"Reply content should not be a dict, got {response_dict}")
        except json.JSONDecodeError:
            pass

        if output_file is not None:
            if not output_file.endswith(f".{file_type}"):
                raise ValueError(f"Output file must have a .{file_type} extension.")
            with open(output_file, "wb") as f:
                _ = f.write(response.content)
        return response.content

    async def request_download(self, url: str, file_path: str) -> bool:
        """Download a file from a URL."""
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS) as r:
                _ = r.raise_for_status()
                with open(file_path, "wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=self.DEFAULT_FILE_CHUNK_SIZE):
                        _ = f.write(chunk)
        return True
