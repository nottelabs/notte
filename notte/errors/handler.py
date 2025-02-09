import logging
from functools import wraps
from typing import Callable, TypeVar

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
                should_retry_later=False,
            ) from e

    return wrapper
