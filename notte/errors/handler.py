import logging
from functools import wraps
from typing import Callable, TypeVar

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from notte.errors.base import NotteBaseError, NotteTimeoutError

T = TypeVar("T")


def handle_errors(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to handle and transform external errors into package-specific errors."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except NotteBaseError as e:
            # Already our error type, just log and re-raise
            logging.error(f"NotteBaseError: {e.dev_message}", exc_info=True)
            raise e
        except TimeoutError as e:
            # Transform external timeout error
            logging.error("Request timed out", exc_info=True)
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


class InvalidLocatorRuntimeError(NotteBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=f"Invalid locator: {message}",
            user_message="Interactive element is not found or not visible. Execution failed.",
            agent_message=(
                "Interactive element is not found or not visible. Execution failed. Hint: wait 5s and try again or try"
                " another action."
            ),
        )


def handle_playwright_errors(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to handle playwright errors."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except NotteBaseError as e:
            # Already our error type, just log and re-raise
            logging.error(f"NotteBaseError: {e.dev_message}", exc_info=True)
            raise e
        except PlaywrightTimeoutError as e:
            # Transform external timeout error
            if "waititing for locator" in str(e):
                raise InvalidLocatorRuntimeError(message=str(e)) from e
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
                agent_message=None,
                should_retry_later=False,
            ) from e

    return wrapper
