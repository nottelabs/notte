import json
import os
import re
import threading
import weakref
from abc import ABC
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator, Mapping, Sequence
from contextlib import ExitStack, asynccontextmanager, contextmanager
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, Self, TypeVar, cast
from urllib.parse import quote, urljoin

import httpx
from notte_core import __version__ as notte_core_version
from notte_core.logging import logger
from pydantic import BaseModel, ConfigDict, ValidationError

from notte_sdk._retry import DEFAULT_MAX_RETRIES
from notte_sdk._transport import (
    AsyncSharedHttpClient,
    SharedHttpClient,
    aiter_lines,
    asend,
    asend_with_retries,
    astream,
    decode_json,
    form_fields,
    http_client,
    iter_lines,
    multipart_files,
    raise_for_status,
    send,
    send_with_retries,
    stream,
    with_query,
)
from notte_sdk.auth import MISSING_API_KEY_MESSAGE, resolve_api_key
from notte_sdk.errors import (
    AuthenticationError,
    NotteAPIError,
    NotteAPIExecutionError,
    NotteConnectionError,
    NotteRequestError,
)

if TYPE_CHECKING:
    from notte_sdk.client import AsyncNotteClient, NotteClient

TResponse = TypeVar("TResponse", bound=BaseModel, covariant=True)
# The client that owns a resource client: `NotteClient` or `AsyncNotteClient`.
TRoot = TypeVar("TRoot")
# A local file to upload: its path, or `(filename, path)` to send it under another name.
UploadFile = str | os.PathLike[str] | tuple[str, str | os.PathLike[str]]

# Global variable to cache PyPI version check result
_cached_pypi_version: str | None = None
_version_check_performed: bool = False


class RawResponse(BaseModel):
    """A JSON object response whose schema has no model in `notte_core.types` yet.

    The generated endpoints (`notte_sdk._generated.endpoints`) parse such responses with this
    class; every field lands in `model_extra` (or `model_dump()`).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


class NotteEndpoint(BaseModel, Generic[TResponse]):
    # Relative to the client's `base_endpoint_path`, or absolute (from the server root) when it
    # starts with "/", as the generated endpoints are.
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


def _build_request(
    client: httpx.Client | httpx.AsyncClient,
    endpoint: NotteEndpoint[TResponse],
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    timeout: float,
) -> httpx.Request:
    """The request `BaseClient._send` and `AsyncBaseClient._send` send for an endpoint."""
    files = multipart_files(endpoint.files) if endpoint.files is not None else None
    headers = dict(headers)
    url = with_query(url, params)
    match endpoint.method:
        case "GET" | "DELETE":
            return client.build_request(endpoint.method, url, headers=headers, timeout=timeout)
        case "POST" | "PATCH":
            content = None
            data = None
            if endpoint.request is None:
                pass
            elif files is None:
                content = endpoint.request.model_dump_json(exclude_none=True)
                headers["Content-Type"] = "application/json"
            else:
                # multipart: the request fields are sent as form fields next to the files
                data = form_fields(endpoint.request.model_dump(exclude_none=True))
            return client.build_request(
                endpoint.method,
                url,
                headers=headers,
                content=content,
                data=data,
                files=files,
                timeout=timeout,
            )


def _json_post(
    client: httpx.Client | httpx.AsyncClient,
    endpoint: NotteEndpoint[TResponse],
    *,
    url: str,
    headers: dict[str, str],
    timeout: float,
) -> httpx.Request:
    """The POST that `_request_once` and `_stream_lines` send: the request model as JSON."""
    content = endpoint.request.model_dump_json(exclude_none=True) if endpoint.request is not None else ""
    return client.build_request("POST", url, headers=headers, content=content, timeout=timeout)


@contextmanager
def _open_uploads(files: Mapping[str, UploadFile]) -> Generator[dict[str, Any]]:
    """Open the local files of a multipart upload for one request and close them afterwards."""
    with ExitStack() as stack:
        uploads: dict[str, Any] = {}
        for name, upload in files.items():
            filename, path = upload if isinstance(upload, tuple) else (None, upload)
            if not os.path.exists(path):
                raise ValueError("The file doesn't exist!")
            handle = stack.enter_context(open(path, "rb"))
            uploads[name] = handle if filename is None else (filename, handle)
        yield uploads


class _ClientCore(ABC, Generic[TRoot]):
    """What `BaseClient` and `AsyncBaseClient` share: configuration, headers, paths and response checks.

    Neither subclass decides anything about a request or response on its own: the sync
    and async I/O methods only send, read and await.
    """

    # Whether the once-per-process PyPI version check runs on a background thread.
    _check_version_in_background: ClassVar[bool] = False

    DEFAULT_NOTTE_API_URL: ClassVar[str] = "https://api.notte.cc"
    DEFAULT_REQUEST_TIMEOUT_SECONDS: ClassVar[int] = 60
    DEFAULT_FILE_CHUNK_SIZE: ClassVar[int] = 8192

    HEALTH_CHECK_ENDPOINT: ClassVar[str] = "health"
    REQUEST_ORIGIN: ClassVar[str] = "sdk-python"

    # Set per instance in __init__. Declared here with a default so clients
    # built without running __init__ still resolve it.
    db_preview: str | None = None

    def __init__(
        self,
        root_client: TRoot,
        base_endpoint_path: str | None,
        server_url: str | None = None,
        api_key: str | None = None,
        verbose: bool = False,
    ):
        self.root_client: TRoot = root_client
        self.server_url: str = server_url or os.getenv("NOTTE_API_URL") or self.DEFAULT_NOTTE_API_URL
        token = resolve_api_key(api_key, self.server_url)
        if token is None:
            raise AuthenticationError(MISSING_API_KEY_MESSAGE)
        self.token: str = token
        self.base_endpoint_path: str | None = base_endpoint_path
        self.verbose: bool = verbose
        self.db_preview = (os.getenv("NOTTE_DB_PREVIEW_BRANCH") or "").strip() or None

        # Check for version mismatch and warn user if needed
        self.check_and_warn_version_mismatch()

    @property
    def max_retries(self) -> int:
        """Retries for transient failures, from ``NotteClient(max_retries=...)``."""
        value = getattr(self.root_client, "max_retries", DEFAULT_MAX_RETRIES)
        return value if isinstance(value, int) and not isinstance(value, bool) else DEFAULT_MAX_RETRIES

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
            NotteRequestError: If the PyPI API request fails
            KeyError: If the package is not found or the response format is unexpected
        """
        try:
            # Include proper User-Agent header as recommended by PyPI
            headers = {"User-Agent": f"notte-sdk/{notte_core_version} (https://github.com/NotteAI/notte)"}

            with http_client() as client:
                response = send(
                    client,
                    client.build_request(
                        "GET",
                        f"https://pypi.org/pypi/{package_name}/json",
                        headers=headers,
                        timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
                    ),
                )
            raise_for_status(response)

            data = decode_json(response)
            return data["info"]["version"]

        except NotteRequestError as e:
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

        if self._check_version_in_background:
            # A blocking PyPI request; async clients are often created inside a running event loop.
            threading.Thread(target=self._warn_if_outdated, name="notte-sdk-version-check", daemon=True).start()
        else:
            self._warn_if_outdated()

    def _warn_if_outdated(self) -> None:
        global _cached_pypi_version
        try:
            # Get latest version from PyPI
            latest_version = self._get_latest_pypi_version("notte-sdk")
            _cached_pypi_version = latest_version

            # Compare versions and warn only if current version is older than PyPI version
            if self._is_version_older(notte_core_version, latest_version):
                logger.warning(
                    f"⚠️ You are using notte-sdk version {notte_core_version}, but version {latest_version} is available on PyPI. Run 'pip install notte-sdk=={latest_version}' to avoid any interruptions."
                )

        except Exception:
            # Silently fail - don't disrupt user experience if version check fails
            pass

    def _is_version_older(self, current_version: str, latest_version: str) -> bool:
        """
        Check if the current version is older than the latest version.

        Args:
            current_version: The current version string (e.g., "1.7.4")
            latest_version: The latest version string from PyPI (e.g., "1.7.3")

        Returns:
            True if current_version is older than latest_version, False otherwise
        """
        try:
            # Parse version strings into comparable tuples
            current_parts = [int(x) for x in current_version.split(".")]
            latest_parts = [int(x) for x in latest_version.split(".")]

            # Pad with zeros if lengths differ
            max_len = max(len(current_parts), len(latest_parts))
            current_parts.extend([0] * (max_len - len(current_parts)))
            latest_parts.extend([0] * (max_len - len(latest_parts)))

            # Return True only if current version is strictly less than latest
            return current_parts < latest_parts
        except (ValueError, AttributeError):
            # If version parsing fails, don't suggest upgrade
            return False

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

        # Use the centralized version comparison logic
        should_suggest = self._is_version_older(notte_core_version, _cached_pypi_version)
        return should_suggest, _cached_pypi_version

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

    def headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """
        Return HTTP headers for authenticated API requests.

        Constructs and returns a dictionary containing the 'Authorization' header,
        which is formatted as a Bearer token using the API key stored in self.token.
        Also includes headers to identify the request as coming from the SDK.
        """
        # Internal: when NOTTE_DB_PREVIEW_BRANCH names a branch, forward it so the
        # API serves the request from that branch's database. Only meaningful
        # against our own non-production deployments, which is why it is not
        # part of the documented interface.
        preview = {"x-db-preview": self.db_preview} if self.db_preview else {}
        return {
            "Authorization": f"Bearer {self.token}",
            "x-notte-sdk-version": notte_core_version,
            "x-notte-request-origin": self.REQUEST_ORIGIN,
            **preview,
            **(
                {"x-notte-auth-capability": os.environ["NOTTE_AUTH_CAPABILITY"]}
                if os.getenv("NOTTE_AUTH_CAPABILITY")
                else {}
            ),
            **(headers or {}),
        }

    def _with_db_preview(self, url: str) -> str:
        """Add the preview-branch selector to a websocket URL.

        A WebSocket handshake carries no request headers when it is opened from
        a browser, so the branch travels in the query string instead. Returns
        the URL unchanged when no branch is configured.

        Only pass urls served by this API. A session can be backed by a
        third-party browser provider, and handing that provider an internal
        branch name is both meaningless to it and more than it needs to know.
        """
        if self.db_preview:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}db_preview={quote(self.db_preview, safe='')}"
        return url

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

        # Add base endpoint path if it exists (absolute paths start at the server root)
        if self.base_endpoint_path is not None and not endpoint.path.startswith("/"):
            # Remove any leading/trailing slashes and append with trailing slash
            base_path = self.base_endpoint_path.strip("/")
            if base_path:
                path = urljoin(path, base_path + "/")

        # Add the endpoint path, removing any leading slashes
        endpoint_path = endpoint.path.lstrip("/")
        path = urljoin(path, endpoint_path)
        return path

    def _error_path(self, endpoint: NotteEndpoint[TResponse]) -> str:
        """The endpoint's path for error messages, e.g. `personas/<id>`."""
        if endpoint.path.startswith("/"):
            return endpoint.path.lstrip("/")
        return f"{self.base_endpoint_path}/{endpoint.path}"

    def _prepare(
        self, endpoint: NotteEndpoint[TResponse], headers: dict[str, str] | None
    ) -> tuple[str, dict[str, str], dict[str, Any] | None]:
        """The URL, headers and query parameters of an endpoint's request."""
        headers = self.headers(headers=headers)
        url = self.request_path(endpoint)
        params = endpoint.params.model_dump(exclude_none=True) if endpoint.params is not None else None
        if self.verbose:
            logger.info(f"Making `{endpoint.method}` request to `{endpoint.path}` with params `{params}`.")
        return url, headers, params

    def _check_status(self, endpoint: NotteEndpoint[TResponse], response: httpx.Response) -> None:
        """Raise the matching error for a non-2xx response, whose body was read."""
        if not 200 <= response.status_code < 300:
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
                raise NotteAPIExecutionError(path=self._error_path(endpoint), response=response)

            raise NotteAPIError(path=self._error_path(endpoint), response=response)

    def _decode(self, endpoint: NotteEndpoint[TResponse], response: httpx.Response, check_response_detail: bool) -> Any:
        """The JSON body of a successful response; `{}` when it has none."""
        if response.status_code == 204 or getattr(response, "content", None) == b"":
            return {}
        response_dict: Any = decode_json(response)
        if check_response_detail and isinstance(response_dict, dict) and "detail" in response_dict:
            raise NotteAPIError(path=self._error_path(endpoint), response=response)
        return cast(Any, response_dict)

    def _validate(self, endpoint: NotteEndpoint[TResponse], response: Any) -> TResponse:
        """Parse a decoded JSON object with the endpoint's response model."""
        if not isinstance(response, dict):
            raise NotteAPIError(path=self._error_path(endpoint), response=response)

        try:
            return endpoint.response.model_validate(response, context={"sdk_response": True})
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

    def _validate_list(self, endpoint: NotteEndpoint[TResponse], response_list: Any) -> Sequence[TResponse]:
        """Parse a decoded JSON list, or a page's `items`, with the endpoint's response model."""
        if not isinstance(response_list, list):
            if "items" in response_list:
                response_list = response_list["items"]
            if not isinstance(response_list, list):
                raise NotteAPIError(path=self._error_path(endpoint), response=response_list)

        try:
            return [endpoint.response.model_validate(item, context={"sdk_response": True}) for item in response_list]  # pyright: ignore[reportUnknownVariableType]
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


class BaseClient(_ClientCore["NotteClient"]):
    # Connections of a client built without a NotteClient, opened on first use.
    _own_http: SharedHttpClient | None = None

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

        Sets up the client by resolving an API key from the provided parameter, the
        NOTTE_API_KEY environment variable, or the notte-cli keyring. Selects the server
        URL (defaulting to a preconfigured server if none is provided), initializes a
        mapping of endpoints using the implemented 'endpoints' method, and stores an
        optional base endpoint path for constructing request URLs.

        Args:
            base_endpoint_path: Optional base path to be prefixed to endpoint URLs.
            api_key: Optional API key for authentication; if not supplied, retrieved from
                the NOTTE_API_KEY environment variable or the notte-cli keyring.

        Raises:
            AuthenticationError: If an API key cannot be resolved.
        """
        super().__init__(root_client, base_endpoint_path, server_url=server_url, api_key=api_key, verbose=verbose)

    @property
    def http(self) -> httpx.Client:
        """The pooled HTTP client shared by every resource of the owning `NotteClient`."""
        shared = getattr(self.root_client, "_http", None)
        if not isinstance(shared, SharedHttpClient):
            shared = self._own_http
            if shared is None:
                shared = self._own_http = SharedHttpClient()
                _ = weakref.finalize(self, shared.close)
        return shared.get()

    def health_check(self) -> None:
        """
        Health check the Notte API.
        """
        try:
            response = send(
                self.http,
                self.http.build_request(
                    "GET",
                    f"{self.server_url}/{self.HEALTH_CHECK_ENDPOINT}",
                    headers={"x-notte-request-origin": self.REQUEST_ORIGIN, "x-notte-sdk-version": notte_core_version},
                ),
            )
            if response.status_code != 200:
                logger.error(f"⚠️ Health check failed with status code {response.status_code}.")
                raise Exception(
                    f"Health check failed with status code {response.status_code}. Please check your server URL."
                )
        except NotteConnectionError as e:
            logger.error(f"⚠️ Health check failed with error: {e}. Please check your server URL.")
            raise Exception(
                "Health check failed because the server is not reachable. Please check your server URL."
            ) from e
        logger.info("🔥 Health check passed. API ready to serve requests.")

    def _request(
        self,
        endpoint: NotteEndpoint[TResponse],
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        *,
        check_response_detail: bool = True,
    ) -> Any:
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
        response = self._send_checked(endpoint, headers=headers, timeout=timeout)
        return self._decode(endpoint, response, check_response_detail)

    def _send_checked(
        self, endpoint: NotteEndpoint[TResponse], *, headers: dict[str, str] | None, timeout: float | None
    ) -> httpx.Response:
        """Send `endpoint` with retries; a non-2xx response raises the matching error."""
        url, headers, params = self._prepare(endpoint, headers)
        response = send_with_retries(
            endpoint,
            lambda remaining: self._send(endpoint, url=url, headers=headers, params=params, timeout=remaining),
            max_retries=self.max_retries,
            timeout=timeout or self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        self._check_status(endpoint, response)
        return response

    def _send(
        self,
        endpoint: NotteEndpoint[TResponse],
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        timeout: float | None,
    ) -> httpx.Response:
        request = _build_request(
            self.http,
            endpoint,
            url=url,
            headers=headers,
            params=params,
            timeout=timeout or self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        return send(self.http, request)

    def request(
        self, endpoint: NotteEndpoint[TResponse], headers: dict[str, str] | None = None, timeout: float | None = None
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
        return self._validate(endpoint, response)

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
        return self._validate_list(endpoint, response_list)

    def _request_upload(self, endpoint: NotteEndpoint[TResponse], files: Mapping[str, UploadFile]) -> TResponse:
        """
        Sends the endpoint as multipart form data with local files attached, and returns the validated response.

        The endpoint's request model is sent as the form fields. Each file is opened for the request
        and closed afterwards; retries resend it from the start.

        Args:
            endpoint: The API endpoint to send.
            files: Form field name to the local file to upload, or to `(filename, path)` to send it under another name.

        Raises:
            ValueError: If a file does not exist.
        """
        with _open_uploads(files) as uploads:
            return self.request(endpoint.model_copy(update={"files": uploads}))

    def _request_bytes(self, endpoint: NotteEndpoint[TResponse]) -> bytes:
        """
        Sends the endpoint and returns its raw response body, for operations that respond with a file.

        Raises:
            NotteAPIError: If the API response indicates a failure.
        """
        return self._send_checked(endpoint, headers=None, timeout=None).content

    @contextmanager
    def _stream_bytes(self, endpoint: NotteEndpoint[TResponse]) -> Generator[Iterator[bytes], None, None]:
        """
        Sends the GET endpoint once and yields its response body in chunks, without holding it in memory.

        Raises:
            NotteAPIError: If the API response indicates a failure.
        """
        request = self.http.build_request(
            "GET", self.request_path(endpoint), headers=self.headers(), timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS
        )
        with stream(self.http, request) as response:
            if response.is_error:
                _ = response.read()
                raise NotteAPIError(path=self._error_path(endpoint), response=response)
            yield (chunk for chunk in response.iter_bytes(self.DEFAULT_FILE_CHUNK_SIZE) if chunk)

    def _request_once(self, endpoint: NotteEndpoint[TResponse], *, headers: dict[str, str], timeout: float) -> Any:
        """
        Sends the endpoint's JSON request once, without retries, and returns the decoded JSON response.

        Raises:
            NotteAPIError: If the API response indicates a failure.
        """
        response = send(self.http, self._once_request(endpoint, headers=headers, timeout=timeout))
        if response.is_error:
            raise NotteAPIError(path=self._error_path(endpoint), response=response)
        return decode_json(response)

    @contextmanager
    def _stream_lines(
        self, endpoint: NotteEndpoint[TResponse], *, headers: dict[str, str], timeout: float
    ) -> Generator[Iterator[str], None, None]:
        """
        Sends the endpoint's JSON request once, without retries, and yields the response's non-empty lines
        as they arrive, decoded as UTF-8: the server-sent events of a streaming response.

        Raises:
            NotteAPIError: If the API response indicates a failure.
        """
        with stream(self.http, self._once_request(endpoint, headers=headers, timeout=timeout)) as response:
            if response.is_error:
                _ = response.read()
                raise NotteAPIError(path=self._error_path(endpoint), response=response)
            yield (line.decode("utf-8") for line in iter_lines(response) if line)

    def _once_request(
        self, endpoint: NotteEndpoint[TResponse], *, headers: dict[str, str], timeout: float
    ) -> httpx.Request:
        """The POST that `_request_once` and `_stream_lines` send: the request model as JSON."""
        headers = self.headers(headers={**headers, "Content-Type": "application/json"})
        return _json_post(self.http, endpoint, url=self.request_path(endpoint), headers=headers, timeout=timeout)

    def _request_file(
        self, endpoint: NotteEndpoint[TResponse], file_type: str, output_file: str | None = None
    ) -> bytes:
        url = self.request_path(endpoint)
        response = send(
            self.http,
            self.http.build_request("GET", url, headers=self.headers(), timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS),
        )

        try:
            response_dict: Any = response.json()
            if isinstance(response_dict, dict) and "detail" in response_dict:
                raise ValueError(cast(dict[str, Any], response_dict)["detail"])
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
        request = self.http.build_request("GET", url, timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS)
        with stream(self.http, request) as r:
            raise_for_status(r)

            with open(file_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=self.DEFAULT_FILE_CHUNK_SIZE):
                    _ = f.write(chunk)

        return True


class AsyncBaseClient(_ClientCore["AsyncNotteClient"]):
    """The async twin of `BaseClient`: the same requests, retries and errors on `httpx.AsyncClient`.

    Every method below mirrors the `BaseClient` method of the same name.
    """

    # Connections of a client built without an AsyncNotteClient, opened on first use.
    _own_http: AsyncSharedHttpClient | None = None
    _check_version_in_background: ClassVar[bool] = True

    def __init__(
        self,
        root_client: "AsyncNotteClient",
        base_endpoint_path: str | None,
        server_url: str | None = None,
        api_key: str | None = None,
        verbose: bool = False,
    ):
        super().__init__(root_client, base_endpoint_path, server_url=server_url, api_key=api_key, verbose=verbose)

    @property
    def http(self) -> httpx.AsyncClient:
        """The pooled HTTP client shared by every resource of the owning `AsyncNotteClient`.

        Raises `RuntimeError` when used from another event loop than the one that opened it.
        """
        shared = getattr(self.root_client, "_http", None)
        if not isinstance(shared, AsyncSharedHttpClient):
            shared = self._own_http
            if shared is None:
                shared = self._own_http = AsyncSharedHttpClient()
                _ = weakref.finalize(self, shared.warn_unclosed)
        return shared.get()

    async def _request(
        self,
        endpoint: NotteEndpoint[TResponse],
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        *,
        check_response_detail: bool = True,
    ) -> Any:
        """Executes an HTTP request for the given API endpoint and returns the decoded JSON response."""
        response = await self._send_checked(endpoint, headers=headers, timeout=timeout)
        return self._decode(endpoint, response, check_response_detail)

    async def _send_checked(
        self, endpoint: NotteEndpoint[TResponse], *, headers: dict[str, str] | None, timeout: float | None
    ) -> httpx.Response:
        """Send `endpoint` with retries; a non-2xx response raises the matching error."""
        url, headers, params = self._prepare(endpoint, headers)
        response = await asend_with_retries(
            endpoint,
            lambda remaining: self._send(endpoint, url=url, headers=headers, params=params, timeout=remaining),
            max_retries=self.max_retries,
            timeout=timeout or self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        self._check_status(endpoint, response)
        return response

    async def _send(
        self,
        endpoint: NotteEndpoint[TResponse],
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        timeout: float | None,
    ) -> httpx.Response:
        http = self.http
        request = _build_request(
            http,
            endpoint,
            url=url,
            headers=headers,
            params=params,
            timeout=timeout or self.DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        return await asend(http, request)

    async def request(
        self, endpoint: NotteEndpoint[TResponse], headers: dict[str, str] | None = None, timeout: float | None = None
    ) -> TResponse:
        """Requests the specified API endpoint and returns the validated response."""
        return self._validate(endpoint, await self._request(endpoint, headers=headers, timeout=timeout))

    async def request_list(self, endpoint: NotteEndpoint[TResponse]) -> Sequence[TResponse]:
        """Retrieves and validates a list of responses from the API."""
        return self._validate_list(endpoint, await self._request(endpoint))

    async def _request_upload(self, endpoint: NotteEndpoint[TResponse], files: Mapping[str, UploadFile]) -> TResponse:
        """Sends the endpoint as multipart form data with local files attached, and returns the validated response."""
        with _open_uploads(files) as uploads:
            return await self.request(endpoint.model_copy(update={"files": uploads}))

    async def _request_bytes(self, endpoint: NotteEndpoint[TResponse]) -> bytes:
        """Sends the endpoint and returns its raw response body, for operations that respond with a file."""
        return (await self._send_checked(endpoint, headers=None, timeout=None)).content

    @asynccontextmanager
    async def _stream_bytes(self, endpoint: NotteEndpoint[TResponse]) -> AsyncGenerator[AsyncIterator[bytes]]:
        """Sends the GET endpoint once and yields its response body in chunks, without holding it in memory."""
        http = self.http
        request = http.build_request(
            "GET", self.request_path(endpoint), headers=self.headers(), timeout=self.DEFAULT_REQUEST_TIMEOUT_SECONDS
        )
        async with astream(http, request) as response:
            if response.is_error:
                _ = await response.aread()
                raise NotteAPIError(path=self._error_path(endpoint), response=response)
            yield (chunk async for chunk in response.aiter_bytes(self.DEFAULT_FILE_CHUNK_SIZE) if chunk)

    async def _request_once(
        self, endpoint: NotteEndpoint[TResponse], *, headers: dict[str, str], timeout: float
    ) -> Any:
        """Sends the endpoint's JSON request once, without retries, and returns the decoded JSON response."""
        response = await asend(self.http, self._once_request(endpoint, headers=headers, timeout=timeout))
        if response.is_error:
            raise NotteAPIError(path=self._error_path(endpoint), response=response)
        return decode_json(response)

    @asynccontextmanager
    async def _stream_lines(
        self, endpoint: NotteEndpoint[TResponse], *, headers: dict[str, str], timeout: float
    ) -> AsyncGenerator[AsyncIterator[str]]:
        """Sends the endpoint's JSON request once, without retries, and yields the response's non-empty
        lines as they arrive, decoded as UTF-8: the server-sent events of a streaming response."""
        async with astream(self.http, self._once_request(endpoint, headers=headers, timeout=timeout)) as response:
            if response.is_error:
                _ = await response.aread()
                raise NotteAPIError(path=self._error_path(endpoint), response=response)
            yield (line.decode("utf-8") async for line in aiter_lines(response) if line)

    def _once_request(
        self, endpoint: NotteEndpoint[TResponse], *, headers: dict[str, str], timeout: float
    ) -> httpx.Request:
        """The POST that `_request_once` and `_stream_lines` send: the request model as JSON."""
        headers = self.headers(headers={**headers, "Content-Type": "application/json"})
        return _json_post(self.http, endpoint, url=self.request_path(endpoint), headers=headers, timeout=timeout)
