import json
import os
import re
from abc import ABC
from collections.abc import Sequence
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, Self, TypeVar
from urllib.parse import urljoin

import requests
from loguru import logger
from notte_core import __version__ as notte_core_version
from pydantic import BaseModel, ValidationError
from requests.exceptions import ConnectionError

from notte_sdk.errors import AuthenticationError, NotteAPIError, NotteAPIExecutionError

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient

TResponse = TypeVar("TResponse", bound=BaseModel, covariant=True)

# Global variable to cache PyPI version check result
_cached_pypi_version: str | None = None
_version_check_performed: bool = False


class NotteEndpoint(BaseModel, Generic[TResponse]):
    path: str
    response: type[TResponse]
    request: BaseModel | None = None
    method: Literal["GET", "POST", "DELETE", "PATCH"]
    params: BaseModel | None = None
    files: BaseModel | None = None

    def with_request(self, request: BaseModel) -> Self:
        # return deep copy of self with the request set
        """
        Return a deep copy of the endpoint with the specified request.

        Creates a new instance of the endpoint with its request attribute updated to the provided model.
        The original instance remains unmodified.

        Args:
            request: A Pydantic model instance carrying the request data.

        Returns:
            A new endpoint instance with the updated request.
        """
        return self.model_copy(update={"request": request})

    def with_params(self, params: BaseModel) -> Self:
        # return deep copy of self with the params set
        """
        Return a new endpoint instance with updated parameters.

        Creates a copy of the current endpoint with its "params" attribute set to the provided
        Pydantic model.

        Args:
            params: A Pydantic model instance containing the new parameters.
        """
        return self.model_copy(update={"params": params})

    def with_file(self, file_path: str) -> Self:
        """
        Return a new endpoint instance with a file object.

        Args:
            file_path: path to a file to be added to the request
        """
        if not os.path.exists(file_path):
            raise ValueError("The file doesn't exist!")

        file_model = {"file": open(file_path, "rb")}

        return self.model_copy(update={"files": file_model})


class BaseClient(ABC):
    DEFAULT_NOTTE_API_URL: ClassVar[str] = "https://api.notte.cc"
    DEFAULT_REQUEST_TIMEOUT_SECONDS: ClassVar[int] = 60
    DEFAULT_FILE_CHUNK_SIZE: ClassVar[int] = 8192

    HEALTH_CHECK_ENDPOINT: ClassVar[str] = "health"

    def __init__(
        self,
        root_client: "NotteClient",
        base_endpoint_path: str | None,
        server_url: str | None = None,
        api_key: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize a new API client instance.

        Sets up the client by resolving an API key from the provided parameter or the
        NOTTE_API_KEY environment variable. Selects the server URL (defaulting to a
        preconfigured server if none is provided), initializes a mapping of endpoints
        using the implemented 'endpoints' method, and stores an optional base endpoint
        path for constructing request URLs.

        Args:
            base_endpoint_path: Optional base path to be prefixed to endpoint URLs.
            api_key: Optional API key for authentication; if not supplied, retrieved from
                the NOTTE_API_KEY environment variable.

        Raises:
            AuthenticationError: If an API key is neither provided nor available in the environment.
        """
        self.root_client = root_client  # pyright: ignore [reportUnannotatedClassAttribute]
        token = api_key or os.getenv("NOTTE_API_KEY")
        if token is None:
            raise AuthenticationError("NOTTE_API_KEY needs to be provided")
        self.token: str = token
        self.server_url: str = server_url or os.getenv("NOTTE_API_URL") or self.DEFAULT_NOTTE_API_URL
        self.base_endpoint_path: str | None = base_endpoint_path
        self.verbose: bool = verbose

        # Check for version mismatch and warn user if needed
        self.check_and_warn_version_mismatch()

    def is_custom_endpoint_available(self) -> bool:
        """
        Check if the custom endpoint is available.
        """
        if "localhost" in self.server_url:
            return True
        return self.server_url != self.DEFAULT_NOTTE_API_URL

    def _get_latest_pypi_version(self, package_name: str = "notte-sdk") -> str:
        """
        Get the latest version of a package from PyPI.

        This is a private method used internally for version checking.
        PyPI doesn't enforce strict rate limits due to heavy caching and CDN usage,
        but this method follows responsible usage practices.

        Args:
            package_name: The name of the package to check (defaults to "notte-sdk")

        Returns:
            The latest version string from PyPI

        Raises:
            requests.RequestException: If the PyPI API request fails
            KeyError: If the package is not found or the response format is unexpected
        """
        try:
            # Include proper User-Agent header as recommended by PyPI
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
        """
        Check if the current notte-sdk version matches the latest PyPI version.

        This method performs the version check only once per process and caches the result
        globally. If there's a version mismatch, it displays a warning to encourage users
        to upgrade their installation.

        The check is performed silently - if the PyPI request fails, no warning is shown
        to avoid disrupting the user experience. Development versions (containing '.dev')
        are skipped since they're not released on PyPI.
        """
        global _cached_pypi_version, _version_check_performed

        # Only check once per process
        if _version_check_performed:
            return

        _version_check_performed = True

        # Skip version check for development versions
        if ".dev" in notte_core_version:
            return

        try:
            # Get latest version from PyPI
            latest_version = self._get_latest_pypi_version("notte-sdk")
            _cached_pypi_version = latest_version

            # Compare versions and warn if different
            if latest_version != notte_core_version:
                logger.warning(
                    f"⚠️ You are using notte-sdk version {notte_core_version}, but version {latest_version} is available on PyPI. Run 'pip install notte-sdk=={latest_version}' to avoid any interruptions."
                )

        except Exception:
            # Silently fail - don't disrupt user experience if version check fails
            pass

    def _should_suggest_upgrade(self) -> tuple[bool, str | None]:
        """
        Check if we should suggest an upgrade based on version comparison.

        Returns:
            A tuple of (should_suggest, cached_version). should_suggest is True if
            the current version is older than the cached PyPI version.
        """
        global _cached_pypi_version

        if _cached_pypi_version is None:
            return False, None

        # Skip for development versions
        if ".dev" in notte_core_version:
            return False, _cached_pypi_version

        try:
            # Simple version comparison - assumes semantic versioning
            current_parts = [int(x) for x in notte_core_version.split(".")]
            cached_parts = [int(x) for x in _cached_pypi_version.split(".")]

            # Pad with zeros if lengths differ
            max_len = max(len(current_parts), len(cached_parts))
            current_parts.extend([0] * (max_len - len(current_parts)))
            cached_parts.extend([0] * (max_len - len(cached_parts)))

            return current_parts < cached_parts, _cached_pypi_version
        except (ValueError, AttributeError):
            # If version parsing fails, don't suggest upgrade
            return False, _cached_pypi_version

    def _create_upgrade_error_message(
        self, error_context: str, cached_version: str, original_error: str | None = None
    ) -> str:
        """
        Create a standardized upgrade suggestion error message.

        Args:
            error_context: Description of the error context (e.g., "Pydantic validation failed")
            cached_version: The latest available version from PyPI
            original_error: Optional original error message to include

        Returns:
            A formatted error message with upgrade suggestions
        """
        base_message = (
            f"{error_context}. This might be due to API schema changes. "
            f"Current SDK version: {notte_core_version}, Latest available: {cached_version}. "
            f"Either you made a mistake in the request arguments, or you should upgrade to the latest "
            f"notte-sdk version by running: 'pip install notte-sdk=={cached_version}'"
        )

        if original_error:
            base_message += f". Original error: {original_error}"

        return base_message

    def health_check(self) -> None:
        """
        Health check the Notte API.
        """
        try:
            response = requests.get(f"{self.server_url}/{self.HEALTH_CHECK_ENDPOINT}")
            if response.status_code != 200:
                logger.error(f"⚠️ Health check failed with status code {response.status_code}.")
                raise Exception(
                    f"Health check failed with status code {response.status_code}. Please check your server URL."
                )
        except ConnectionError as e:
            logger.error(f"⚠️ Health check failed with error: {e}. Please check your server URL.")
            raise Exception(
                "Health check failed because the server is not reachable. Please check your server URL."
            ) from e
        logger.info("🔥 Health check passed. API ready to serve requests.")

    def headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """
        Return HTTP headers for authenticated API requests.

        Constructs and returns a dictionary containing the 'Authorization' header,
        which is formatted as a Bearer token using the API key stored in self.token.
        """
        return {"Authorization": f"Bearer {self.token}", "x-notte-sdk-version": notte_core_version, **(headers or {})}

    def request_path(self, endpoint: NotteEndpoint[TResponse]) -> str:
        """
        Constructs the full request URL for the given API endpoint.

        If a base endpoint path is defined, the URL is formed by concatenating the server URL,
        the base endpoint path, and the endpoint's path. Otherwise, the endpoint's path is appended
        directly to the server URL.
        """
        # check that not "/{XYZ}" are in the path to avoid missing formated paths (XYZ can be any string)
        unformated_path = re.match(r"/\{\w+\}", endpoint.path)
        if unformated_path:
            raise ValueError(f"Endpoint path cannot contain '{unformated_path.group(0)}' (path={endpoint.path})")
        path = self.server_url.rstrip("/") + "/"

        # Add base endpoint path if it exists
        if self.base_endpoint_path is not None:
            # Remove any leading/trailing slashes and append with trailing slash
            base_path = self.base_endpoint_path.strip("/")
            if base_path:
                path = urljoin(path, base_path + "/")

        # Add the endpoint path, removing any leading slashes
        endpoint_path = endpoint.path.lstrip("/")
        path = urljoin(path, endpoint_path)
        return path

    def _request(
        self, endpoint: NotteEndpoint[TResponse], headers: dict[str, str] | None = None, timeout: int | None = None
    ) -> dict[str, Any]:
        """
        Executes an HTTP request for the given API endpoint.

        Constructs the full URL and headers from the endpoint's configuration and issues an HTTP
        request using the specified method (GET, POST, or DELETE). For POST requests, a request model
        must be provided; otherwise, a ValueError is raised. If the response status code is not 200 or
        the JSON response contains an error detail, a NotteAPIError is raised.

        Args:
            endpoint: An API endpoint instance containing the HTTP method, path, optional request model,
                and query parameters.

        Returns:
            The JSON-decoded response from the API.

        Raises:
            ValueError: If a POST request is attempted without a request model.
            NotteAPIError: If the API response indicates a failure.
        """
        headers = self.headers(headers=headers)
        url = self.request_path(endpoint)
        params = endpoint.params.model_dump(exclude_none=True) if endpoint.params is not None else None
        files = endpoint.files if endpoint.files is not None else None
        json = None
        if self.verbose:
            logger.info(f"Making `{endpoint.method}` request to `{endpoint.path} (i.e `{url}`) with params `{params}`.")
        match endpoint.method:
            case "GET":
                response = requests.get(
                    url=url,
                    headers=headers,
                    params=params,
                    timeout=timeout or self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
                )
            case "POST" | "PATCH":
                if endpoint.request is None and endpoint.files is None:
                    raise ValueError("Request model or file is required for POST requests")
                if endpoint.request is None:
                    data = None
                elif files is None:
                    data = endpoint.request.model_dump_json(exclude_none=True)
                    headers["Content-Type"] = "application/json"
                else:
                    # if files is not None, data must not be a string
                    data = endpoint.request.model_dump(exclude_none=True)
                method = requests.post if endpoint.method == "POST" else requests.patch
                response = method(
                    url=url,
                    headers=headers,
                    data=data,
                    params=params,
                    timeout=timeout or self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
                    files=files,
                    json=json,
                )
            case "DELETE":
                response = requests.delete(
                    url=url,
                    headers=headers,
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

                        # Check if this looks like a Pydantic validation error
                        if (
                            "extra_forbidden" in error_message
                            or "Extra inputs are not permitted" in error_message
                            or "'type':" in error_message
                        ):
                            # Enhance the error with upgrade suggestion
                            upgrade_msg = self._create_upgrade_error_message(
                                "API returned 422 validation error", cached_version, error_message
                            )
                            raise RuntimeError(upgrade_msg)
                    except (JSONDecodeError, KeyError):
                        # If we can't parse the response, fall through to normal error handling
                        pass

            if response.headers.get("x-error-class") == "NotteApiExecutionError":
                raise NotteAPIExecutionError(path=f"{self.base_endpoint_path}/{endpoint.path}", response=response)

            raise NotteAPIError(path=f"{self.base_endpoint_path}/{endpoint.path}", response=response)
        response_dict: Any = response.json()
        if "detail" in response_dict:
            raise NotteAPIError(path=f"{self.base_endpoint_path}/{endpoint.path}", response=response)
        return response_dict

    def request(
        self, endpoint: NotteEndpoint[TResponse], headers: dict[str, str] | None = None, timeout: int | None = None
    ) -> TResponse:
        """
        Requests the specified API endpoint and returns the validated response.

        This method sends an HTTP request according to the endpoint configuration and
        validates that the response is a dictionary. It then parses the response using the
        endpoint's associated response model. If the response is not a dictionary, a
        NotteAPIError is raised.

        Args:
            endpoint: The API endpoint configuration containing request details and the
                      expected response model.

        Returns:
            The validated response parsed using the endpoint's response model.

        Raises:
            NotteAPIError: If the API response is not a dictionary.
        """
        response: Any = self._request(endpoint, headers=headers, timeout=timeout)
        if not isinstance(response, dict):
            raise NotteAPIError(path=f"{self.base_endpoint_path}/{endpoint.path}", response=response)

        try:
            return endpoint.response.model_validate(response)
        except ValidationError as e:
            # Check if we should suggest an upgrade
            should_upgrade, cached_version = self._should_suggest_upgrade()

            if should_upgrade and cached_version:
                # Enhance the error message with upgrade suggestion
                upgrade_msg = self._create_upgrade_error_message("Pydantic validation failed", cached_version)
                # Create a RuntimeError with enhanced message but keep original as cause
                raise RuntimeError(upgrade_msg) from e
            else:
                # Re-raise original error if no upgrade suggestion needed
                raise

    def request_list(self, endpoint: NotteEndpoint[TResponse]) -> Sequence[TResponse]:
        # Handle the case where TResponse is a list of BaseModel
        """
        Retrieves and validates a list of responses from the API.

        This method sends a request using the provided endpoint and expects the response to be a list. Each item is validated
        against the model defined in the endpoint. A NotteAPIError is raised if the response is not a list.

        Parameters:
            endpoint: The API endpoint containing the path and the expected response model.

        Returns:
            A list of validated response items.

        Raises:
            NotteAPIError: If the response is not a list.
        """
        response_list: Any = self._request(endpoint)
        if not isinstance(response_list, list):
            if "items" in response_list:
                response_list = response_list["items"]
            if not isinstance(response_list, list):
                raise NotteAPIError(path=f"{self.base_endpoint_path}/{endpoint.path}", response=response_list)

        try:
            return [endpoint.response.model_validate(item) for item in response_list]  # pyright: ignore[reportUnknownVariableType]
        except ValidationError as e:
            # Check if we should suggest an upgrade
            should_upgrade, cached_version = self._should_suggest_upgrade()

            if should_upgrade and cached_version:
                # Enhance the error message with upgrade suggestion
                upgrade_msg = self._create_upgrade_error_message(
                    "Pydantic validation failed for list response", cached_version
                )
                # Create a RuntimeError with enhanced message but keep original as cause
                raise RuntimeError(upgrade_msg) from e
            else:
                # Re-raise original error if no upgrade suggestion needed
                raise

    def _request_file(
        self, endpoint: NotteEndpoint[TResponse], file_type: str, output_file: str | None = None
    ) -> bytes:
        url = self.request_path(endpoint)
        response = requests.get(
            url=url,
            headers=self.headers(),
            timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )

        try:
            response_dict: Any = response.json()
            if "detail" in response_dict:
                raise ValueError(response_dict["detail"])
            raise ValueError(f"Relpay content should not be a dict, got {response_dict}")
        except json.JSONDecodeError:
            pass

        if output_file is not None:
            if not output_file.endswith(f".{file_type}"):
                raise ValueError(f"Output file must have a .{file_type} extension.")
            with open(output_file, "wb") as f:
                _ = f.write(response.content)
        return response.content

    def request_download(self, url: str, file_path: str) -> bool:
        with requests.get(
            url=url,
            stream=True,
            timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
        ) as r:
            r.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=self.DEFAULT_FILE_CHUNK_SIZE):
                    _ = f.write(chunk)

        return True
