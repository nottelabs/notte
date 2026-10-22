import time
from functools import wraps
from typing import Any, Callable, Protocol, TypeVar

import requests
from notte_core.errors import NotteBaseError
from notte_core.logging import logger

T = TypeVar("T")


class APIResponse(Protocol):
    """The parts of an HTTP response the API errors read.

    The SDK passes an `httpx.Response`. A `requests.Response` built by calling
    code still works.
    """

    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    def json(self) -> Any: ...


class NotteRequestError(requests.RequestException):
    """An HTTP request made by the SDK failed before the API returned a response.

    The SDK's transport errors subclass the matching `requests` exceptions, so
    existing `except requests.RequestException` handlers keep working. Catching
    the `requests` classes is deprecated: catch these classes instead.
    """


class NotteConnectionError(NotteRequestError, requests.ConnectionError):
    """The connection could not be opened, or it broke before a response arrived."""


class NotteProxyError(NotteConnectionError, requests.exceptions.ProxyError):
    """The configured proxy refused or failed the connection."""


class NotteSSLError(NotteConnectionError, requests.exceptions.SSLError):
    """TLS failed, for example because the certificate was rejected."""


class NotteRequestTimeoutError(NotteRequestError, requests.Timeout):
    """The request timed out, or the SDK retry deadline was exceeded."""


class NotteConnectTimeoutError(NotteConnectionError, NotteRequestTimeoutError, requests.ConnectTimeout):
    """Opening the connection timed out. Nothing was sent."""


class NotteReadTimeoutError(NotteRequestTimeoutError, requests.ReadTimeout):
    """The server did not send data in time, after the request was sent."""


class NotteStreamError(NotteRequestError, requests.exceptions.ChunkedEncodingError):
    """The connection broke while the response body was being read."""


class NotteHTTPStatusError(NotteRequestError, requests.HTTPError):
    """A non-API URL (object storage, a download link) answered with a 4xx or 5xx status.

    `response` is the `httpx.Response`: `status_code`, `headers`, `text` and
    `json()` work as they did on `requests.Response`.
    """


class NotteTooManyRedirectsError(NotteRequestError, requests.TooManyRedirects):
    """The server redirected more than 30 times."""


class NotteInvalidURLError(NotteRequestError, requests.exceptions.InvalidURL):
    """The URL is malformed or uses an unsupported scheme."""


# requests.JSONDecodeError.__init__ initializes both json.JSONDecodeError and RequestException.
class NotteJSONDecodeError(NotteRequestError, requests.JSONDecodeError):  # pyright: ignore[reportUnsafeMultipleInheritance]
    """A successful response did not contain valid JSON. Also a `json.JSONDecodeError`."""

    def __init__(self, msg: str, doc: str, pos: int) -> None:
        requests.JSONDecodeError.__init__(self, msg, doc, pos)


class NotteAPIError(NotteBaseError):
    def __init__(self, path: str, response: APIResponse) -> None:
        self.error: dict[Any, Any] = {}
        self.status_code: int = response.status_code
        try:
            self.error = response.json()
        except Exception:
            # Don't re-raise here: non-JSON responses (502s, empty bodies, HTML error
            # pages) must still produce a proper NotteAPIError so callers can rely on
            # `status_code` and catch NotteBaseError.  Previously this raised a raw
            # ValueError(response), which bypassed super().__init__() and caused
            # downstream TypeError crashes in user error-handling code.
            if hasattr(response, "text"):
                self.error["message"] = response.text
            else:
                logger.error(f"Response is not a valid JSON: {response}")

        super().__init__(
            dev_message=f"Request to `{path}` failed with status code {self.status_code}: {self.error}",
            user_message=f"Request to `{path}` failed with status code {self.status_code}: {self.error}",
            should_notify_team=True,
            # agent message not relevant here
            agent_message=None,
        )


class NotteAPIExecutionError(NotteBaseError):
    def __init__(self, path: str, response: APIResponse) -> None:
        try:
            error = response.json()
        except Exception:
            # Same fix as NotteAPIError: don't re-raise a ValueError when the
            # response body isn't valid JSON.  Fall through so super().__init__()
            # is always called and callers get a proper NotteAPIExecutionError.
            error = response.text if hasattr(response, "text") else str(response)

        message = f"Error on {path}: {error}"
        super().__init__(
            dev_message=message,
            user_message=message,
            should_notify_team=True,
            # agent message not relevant here
            agent_message=None,
        )


class AuthenticationError(NotteBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=f"Authentication failed. {message}",
            user_message="Authentication failed. Please check your credentials or upgrade your plan.",
            should_retry_later=False,
            # agent message not relevant here
            agent_message=None,
        )


class InvalidRequestError(NotteBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=f"Invalid request. {message}",
            user_message="Invalid request. Please check your request parameters.",
            should_retry_later=False,
            # agent message not relevant here
            agent_message=None,
        )


def retry(
    max_tries: int,
    delay_seconds: float = 5.0,
    error_message: str = "An error occurred while executing the function. Try again later...",
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    A decorator that retries a function if it raises specified exceptions.

    Args:
        max_tries: Maximum number of attempts to retry the function
        delay_seconds: Time to wait between retries in seconds
        exceptions: Tuple of exception types to catch and retry
        logger: Optional logger instance to use for logging retries

    Returns:
        The decorated function that implements the retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(max_tries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_tries - 1:  # Don't sleep on the last attempt
                        logger.warning(
                            (f"Failed to execute {func.__name__}: {str(e)} (attempt {attempt + 1}/{max_tries})")
                        )
                        time.sleep(delay_seconds)
                    continue

            if last_exception is not None:
                raise RuntimeError(error_message) from last_exception

            # This should never happen but makes the type checker happy
            raise RuntimeError("Unexpected error in retry decorator")

        return wrapper

    return decorator
