import time
from functools import wraps
from typing import Any, Callable, TypeVar

from loguru import logger
from notte_core.errors.base import NotteBaseError
from requests import Response

T = TypeVar("T")


class NotteAPIError(NotteBaseError):
    def __init__(self, path: str, response: Response) -> None:
        try:
            error = response.json()
        except Exception:
            if hasattr(response, "text"):
                error = response.text
            raise ValueError(response)

        super().__init__(
            dev_message=f"Request to `{path}` failed with status code {response.status_code}: {error}",
            user_message=f"Request to `{path}` failed with status code {response.status_code}: {error}",
            should_notify_team=True,
            # agent message not relevant here
            agent_message=None,
        )


class NotteAPIExecutionError(NotteBaseError):
    def __init__(self, path: str, response: Response) -> None:
        try:
            error = response.json()
        except Exception:
            if hasattr(response, "text"):
                error = response.text
            raise ValueError(response)

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
