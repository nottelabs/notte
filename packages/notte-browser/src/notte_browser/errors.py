from collections.abc import Awaitable
from functools import wraps
from typing import Any, Callable, TypeVar

from loguru import logger
from notte_core.errors.base import NotteBaseError, NotteTimeoutError, UnexpectedBehaviorError
from notte_core.errors.processing import InvalidInternalCheckError
from patchright.async_api import Error as PlayrightError
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

T = TypeVar("T")

# #######################################################
# #################### Browser errors ###################
# #######################################################


class BrowserError(NotteBaseError):
    """Base class for Browser related errors."""

    pass


class PageLoadingError(BrowserError):
    def __init__(self, url: str) -> None:
        super().__init__(
            dev_message=f"Failed to load page from {url}. Check if the URL is reachable.",
            user_message="Failed to load page from the given URL. Check if the URL is reachable.",
            agent_message=(
                f"Failed to load page from {url}. Hint: check if the URL is valid and reachable and wait a couple"
                " seconds before retrying. Otherwise, try another URL."
            ),
            should_retry_later=True,
        )


class InvalidURLError(BrowserError):
    def __init__(
        self,
        url: str,
    ) -> None:
        super().__init__(
            dev_message=(
                f"Invalid URL: {url}. Check if the URL is reachable. URLs should start with https:// or http://. "
            ),
            user_message=(
                "Impossible to access the given URL. Check if the URL is reachable. "
                "Remember that URLs should start with https:// or http://"
            ),
            agent_message=f"Invalid URL: {url}. Hint: URL should start with https:// or http://.",
            should_retry_later=False,
        )


class BrowserNotStartedError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message=(
                "Browser not started. You should use `await browser.start()` to start a new session "
                "(or `await env.start()`)."
            ),
            user_message="Session not started. Please start a new session to continue.",
            agent_message="Browser not started. Terminate the current session and start a new one.",
            should_retry_later=False,
        )


class RemoteDebuggingNotAvailableError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="Remote debugging is not available. You should use a `local_pool` instead of a `remote_pool`.",
            user_message="Remote debugging is not available. Please use a `local_pool` instead of a `remote_pool`.",
            agent_message="Remote debugging is not available. Please use a `local_pool` instead of a `remote_pool`.",
            should_retry_later=False,
        )


class BrowserPoolNotStartedError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="Browser pool not started. You should use `await pool.start()` to start the pool.",
            user_message="Browser pool not started. Please start the pool to continue.",
            agent_message="Browser pool not started. Please start the pool to continue.",
            should_retry_later=False,
        )


class BrowserExpiredError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message=(
                "Browser or context expired or closed. You should use `await browser.start()` to start a new session."
            ),
            user_message="Session expired or closed. Create a new session to continue.",
            agent_message="Browser or context expired or closed. Terminate the current session and start a new one.",
            should_retry_later=False,
        )


class EmptyPageContentError(BrowserError):
    def __init__(self, url: str, nb_retries: int) -> None:
        super().__init__(
            dev_message=(
                f"Browser snapshot failed after {nb_retries} retries to get a non-empty web page for: {url}. "
                "Notte cannot continue without a valid page. Try to increase the short waiting time in "
                "`notte.browser.window.py`."
            ),
            user_message="Webpage appears to be empty and cannot be processed.",
            agent_message=(
                "Webpage appears to be empty at the moment. Hint: wait a couple seconds and resume browsing to see if"
                " the problem persist. Otherwise, try another URL."
            ),
            should_retry_later=True,
            should_notify_team=True,
        )


class UnexpectedBrowserError(BrowserError):
    def __init__(self, url: str) -> None:
        super().__init__(
            dev_message=f"Unexpected error detected: {url}. Notte cannot continue without a valid page. ",
            user_message="An unexpected error occurred within the browser session.",
            agent_message=(
                "An unexpected error occurred within the browser session. Hint: wait a couple seconds and retry the"
                " action. Otherwise, try another URL."
            ),
            should_retry_later=True,
            should_notify_team=True,
        )


class BrowserResourceNotFoundError(BrowserError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=message,
            user_message="The requested browser resource was not found. Please start a new session.",
            agent_message=(
                "The requested browser resource was not found. Hint: terminate the current session and start a new one."
            ),
            should_retry_later=False,
        )


class BrowserResourceLimitError(BrowserError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=message,
            user_message="Sorry, we are experiencing high traffic at the moment. Try again later with a new session.",
            agent_message=(
                "The browser is currently experiencing high traffic. Wait 30 seconds before retrying to create a new"
                " session."
            ),
            should_retry_later=False,
        )


# #######################################################
# ################ Environment errors ###################
# #######################################################


class NoSnapshotObservedError(UnexpectedBehaviorError):
    def __init__(self) -> None:
        super().__init__(
            message="Tried to access `env.snapshot` but no snapshot is available in the environment",
            advice="You should use `await env.observe()` first to get a snapshot",
        )


class MaxStepsReachedError(NotteBaseError):
    def __init__(self, max_steps: int) -> None:
        super().__init__(
            dev_message=(
                f"Max number steps reached: {max_steps} in the currrent trajectory. Either use "
                "`env.reset()` to reset the environment or increase max steps in `NotteEnv(max_steps=..)`."
            ),
            user_message=(
                f"Too many actions executed in the current session (i.e. {max_steps} actions). "
                "Please start a new session to continue."
            ),
            # same as user message
            agent_message=None,
        )


# #######################################################
# ################# Resolution errors ###################
# #######################################################


class FailedNodeResolutionError(InvalidInternalCheckError):
    def __init__(self, node_id: str):
        super().__init__(
            check=f"No selector found for action {node_id}",
            url=None,
            dev_advice=(
                "This technnically should never happen. There is likely an issue during playright "
                "conflict resolution pipeline, i.e `ActionResolutionPipe`."
            ),
        )


# #######################################################
# ################# Playwright errors ###################
# #######################################################


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


def capture_playwright_errors(verbose: bool = False):
    """Decorator to handle playwright errors.

    Args:
        verbose (bool): Whether to log detailed debugging information
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await func(*args, **kwargs)
            except NotteBaseError as e:
                # Already our error type, just log and re-raise
                logger.error(f"NotteBaseError: {e.dev_message if verbose else e.user_message}")
                raise e
            except PlaywrightTimeoutError as e:
                # only timeout issue if the last line is it
                # otherwise more generic error
                if "- waiting for locator(" in str(e).strip().split("\n")[-1]:
                    raise InvalidLocatorRuntimeError(message=str(e)) from e
                raise PlaywrightRuntimeError(message=str(e)) from e
            except TimeoutError as e:
                raise NotteTimeoutError(message="Request timed out.") from e
            # Add more except blocks for other external errors
            except PlayrightError as e:
                raise NotteBaseError(
                    dev_message=f"Unexpected playwright error: {str(e)}",
                    user_message="An unexpected error occurred. Our team has been notified.",
                    agent_message=f"An unexpected playwright error occurred: {str(e)}.",
                ) from e
            except Exception as e:
                # Catch-all for unexpected errors
                logger.error(
                    "Unexpected error occurred. Please use the NotteBaseError class to handle this error.",
                    exc_info=verbose,
                )
                raise NotteBaseError(
                    dev_message=f"Unexpected error: {str(e)}",
                    user_message="An unexpected error occurred. Our team has been notified.",
                    agent_message="An unexpected error occurred. You can try again later.",
                    should_retry_later=False,
                ) from e

        return wrapper

    return decorator
