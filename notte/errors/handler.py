import logging
from collections.abc import Awaitable
from functools import wraps
from typing import Callable, TypeVar

from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from notte.errors.base import NotteBaseError, NotteTimeoutError

T = TypeVar("T")


class InvalidLocatorRuntimeError(NotteBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=(
                f"Invalid Playwright locator. Interactive element is not found or not visible. Error:\n{message}"
            ),
            user_message="Interactive element is not found or not visible. Execution failed.",
            agent_message=(
                "Execution failed because interactive element is not found or not visible. "
                "Hint: wait 5s and try again, check for any modal/dialog/popup that might be blocking the element,"
                " or try another action."
            ),
        )


class PlaywrightRuntimeError(NotteBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=f"Playwright runtime error: {message}",
            user_message="An unexpected error occurred. Our team has been notified.",
            agent_message=f"An unexpected error occurred:\n{message}. You should wait a 5s seconds and try again.",
        )


def capture_playwright_errors(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator to handle playwright errors."""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        try:
            return await func(*args, **kwargs)
        except NotteBaseError as e:
            # Already our error type, just log and re-raise
            logging.error(f"NotteBaseError: {e.dev_message}")
            raise e
        except PlaywrightTimeoutError as e:
            # logging.error(f"PlaywrightTimeoutError with message: {e.message}")
            # Transform external timeout error
            if "- waiting for locator(" in str(e):
                raise InvalidLocatorRuntimeError(message=str(e)) from e
            raise PlaywrightRuntimeError(message=str(e)) from e
        except TimeoutError as e:
            raise NotteTimeoutError(message="Request timed out.") from e
        # Add more except blocks for other external errors
        except Exception as e:
            # Catch-all for unexpected errors
            logging.error(
                "Unexpected error occurred. Please use of the NotteBaseError class to handle this error.", exc_info=True
            )
            raise NotteBaseError(
                dev_message=f"Unexpected error: {str(e)}",
                user_message="An unexpected error occurred. Our team has been notified.",
                agent_message="An unexpected error occurred. You can try again later.",
                should_retry_later=False,
            ) from e

    return wrapper
