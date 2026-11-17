import re
import time
from functools import wraps
from typing import Any, Callable, ClassVar, Literal, Protocol, TypedDict, TypeVar

import requests
from notte_core.errors import NotteBaseError
from notte_core.logging import logger

T = TypeVar("T")


class FunctionError(Exception):
    """Base for errors a Notte Function raises to tell the runtime how to treat a failure.

    Only meaningful inside the Notte Functions runtime; locally it is a normal exception.
    Subclass `ExpectedFunctionError` or `RetryableFunctionError` rather than this class,
    and override the class attributes to describe your error:

    - `heal`: whether self-healing may rewrite the function after this failure.
    - `retry`: whether the caller can safely retry the run. The platform never re-runs it.
    - `status_code`: the HTTP status that describes the failure. Informational: the run
      response is still HTTP 200, with the status in its `error` payload.
    - `code`: a stable machine-readable code. Defaults to the class name in snake_case
      (`AccountNotUnique` becomes `account_not_unique`).

    Mix them with built-in exceptions; `except ValueError` still catches this one:

    ```python
    from notte_sdk.errors import ExpectedFunctionError

    class AccountNotUnique(ValueError, ExpectedFunctionError):
        status_code = 409

    def run(email: str):
        accounts = find_accounts(email)
        if len(accounts) != 1:
            raise AccountNotUnique(f"{len(accounts)} accounts match {email}")
    ```
    """

    heal: ClassVar[bool] = True
    retry: ClassVar[bool] = False
    status_code: ClassVar[int] = 500
    code: ClassVar[str | None] = None


class ExpectedFunctionError(FunctionError):
    """A deliberate refusal: the function worked and the failure is the correct outcome.

    The run ends with status `rejected` and is never self-healed.
    """

    heal: ClassVar[bool] = False
    status_code: ClassVar[int] = 422


class RetryableFunctionError(FunctionError):
    """A temporary problem, such as a site being down. The run stays `failed` and is not self-healed.

    `retry` tells the caller that running it again may succeed; the platform does not re-run it.
    """

    heal: ClassVar[bool] = False
    retry: ClassVar[bool] = True
    status_code: ClassVar[int] = 503


FunctionErrorKind = Literal["expected", "retryable", "unexpected"]


class FunctionErrorPayload(TypedDict):
    """How the Notte Functions runtime describes an exception raised by a function."""

    kind: FunctionErrorKind
    type: str
    mro: list[str]
    code: str
    message: str
    heal: bool
    retry: bool
    status_code: int
    source: Literal["class", "default"]


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _snake_case(name: str) -> str:
    """`AccountNotUnique` -> `account_not_unique`, `HTTPTimeout` -> `http_timeout`."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def _message(exc: BaseException) -> str:
    try:
        return str(exc)
    except Exception:  # a user-defined __str__ must not break failure reporting
        return f"<unprintable {type(exc).__name__}>"


def function_error_payload(exc: BaseException) -> FunctionErrorPayload:
    """Describe an exception raised by a Notte Function, for the run's `error` field.

    `kind` follows the nearest preset base in the class's MRO: `expected` for
    `ExpectedFunctionError`, `retryable` for `RetryableFunctionError`, otherwise
    `unexpected`. `heal`, `retry` and `status_code` report the class's actual
    attributes, so a subclass that overrides them keeps its kind. Any other
    exception is `unexpected`, may be healed, and has status code 500.
    """
    cls = type(exc)
    mro = [klass.__name__ for klass in cls.__mro__ if klass is not object]
    message = _message(exc)
    if not isinstance(exc, FunctionError):
        return FunctionErrorPayload(
            kind="unexpected",
            type=cls.__name__,
            mro=mro,
            code=_snake_case(cls.__name__),
            message=message,
            heal=True,
            retry=False,
            status_code=500,
            source="default",
        )
    error_cls = type(exc)
    kind: FunctionErrorKind = "unexpected"
    for klass in error_cls.__mro__:
        if klass is ExpectedFunctionError:
            kind = "expected"
            break
        if klass is RetryableFunctionError:
            kind = "retryable"
            break
    code = error_cls.code
    # Read without the declared `int` type: users can assign anything at runtime. An `int`
    # subclass such as `HTTPStatus.CONFLICT` keeps its value; `bool` or "409" falls back to 500.
    raw_status = getattr(error_cls, "status_code", 500)
    status_code = int(raw_status) if isinstance(raw_status, int) and not isinstance(raw_status, bool) else 500
    return FunctionErrorPayload(
        kind=kind,
        type=cls.__name__,
        mro=mro,
        code=code if isinstance(code, str) and code else _snake_case(cls.__name__),
        message=message,
        heal=bool(error_cls.heal),
        retry=bool(error_cls.retry),
        status_code=status_code,
        source="class",
    )


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
