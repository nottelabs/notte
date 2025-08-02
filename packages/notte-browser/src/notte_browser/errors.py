from collections.abc import Awaitable
from functools import wraps
from typing import Any, Callable, TypeVar

from loguru import logger
from notte_core.actions import ToolAction
from notte_core.common.config import config
from notte_core.errors.base import NotteBaseError, NotteTimeoutError
from notte_core.errors.processing import InvalidInternalCheckError

from notte_browser.playwright_async_api import getPlaywrightOrPatchrightError, getPlaywrightOrPatchrightTimeoutError

T = TypeVar("T")


PlaywrightTimeoutError = getPlaywrightOrPatchrightTimeoutError()
PlaywrightError = getPlaywrightOrPatchrightError()

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
                "(or `session.start()`)."
            ),
            user_message="Session not started. Please start a new session to continue.",
            agent_message="Browser not started. Terminate the current session and start a new one.",
            should_retry_later=False,
        )


class CdpConnectionError(BrowserError):
    def __init__(self, cdp_url: str) -> None:
        super().__init__(
            dev_message=f"Failed to connect to CDP: {cdp_url}. Check if the CDP URL is valid.",
            user_message=f"Failed to connect to CDP: {cdp_url}. Check if the CDP URL is valid.",
            agent_message=f"Failed to connect to CDP: {cdp_url}. Check if the CDP URL is valid.",
        )


class FirefoxNotAvailableError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="Firefox is not available. You should use a different browser.",
            user_message="Firefox is not available. You should use a different browser.",
            agent_message="Firefox is not available. You should use a different browser.",
        )


class RemoteDebuggingNotAvailableError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="Remote debugging is not available. You should use a `local_pool` instead of a `remote_pool`.",
            user_message="Remote debugging is not available. Please use a `local_pool` instead of a `remote_pool`.",
            agent_message="Remote debugging is not available. Please use a `local_pool` instead of a `remote_pool`.",
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


class ScrollActionFailedError(BrowserError):
    def __init__(self) -> None:
        message = "Scroll failed. Either the page is not scrollable or there is a focused element blocking the scroll."
        super().__init__(
            dev_message=message,
            user_message=message,
            agent_message=f"{message} Hint: check viewport dimensions or try to close modals and/or hit escape key.",
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


# #######################################################
# ################ Environment errors ###################
# #######################################################


class NoSnapshotObservedError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="Tried to access `session.snapshot` but no snapshot is available in the session.  You should use `session.observe()` first to get a snapshot.",
            user_message="No snapshot is available in the session. You should use `session.observe()` first to get a snapshot",
            agent_message="No snapshot is available in the session. You should use `session.observe()` first to get a snapshot",
            should_retry_later=False,
        )


class NoActionObservedError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="Tried to access `session.action` but no action is available in the session",
            user_message="No action is available in the session. You should use `session.step()` first to get an action",
            agent_message="No action is available in the session. You should use `session.step()` first to get an action",
        )


class MaxStepsReachedError(NotteBaseError):
    def __init__(self, max_steps: int) -> None:
        super().__init__(
            dev_message=(
                f"Max number steps reached: {max_steps} in the currrent trajectory. Either use "
                "`session.reset()` to reset the session or increase max steps in `NotteSession(max_steps=..)`."
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


def capture_playwright_errors():
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
                logger.error(f"NotteBaseError: {e.dev_message if config.verbose else e.user_message}")
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
            except PlaywrightError as e:
                raise NotteBaseError(
                    dev_message=f"Unexpected playwright error: {str(e)}",
                    user_message="An unexpected error occurred. Our team has been notified.",
                    agent_message=f"An unexpected playwright error occurred: {str(e)}.",
                ) from e
            except Exception as e:
                # Catch-all for unexpected errors
                logger.error(
                    f"Unexpected error occurred. Please use the NotteBaseError class to handle this error. {str(e)}",
                    exc_info=config.verbose,
                )
                raise NotteBaseError(
                    dev_message=f"Unexpected error: {str(e)}",
                    user_message="An unexpected error occurred. Our team has been notified.",
                    agent_message="An unexpected error occurred. You can try again later.",
                    should_retry_later=False,
                ) from e

        return wrapper

    return decorator


# #######################################################
# ################## Storage errors #####################
# #######################################################
class FailedToUploadFileError(NotteBaseError):
    def __init__(self, action_id: str, file_path: str, error: Exception) -> None:
        super().__init__(
            dev_message=f"UploadFileAction failed for id={action_id}, file_path={file_path}: {error}",
            user_message="File upload failed.",
            agent_message=f"The action: {action_id} could not be associated with a file upload action. Hint: find a different element to use for the UploadFileAction.",
        )


class FailedToGetFileError(NotteBaseError):
    def __init__(self, action_id: str, file_path: str) -> None:
        super().__init__(
            dev_message=f"UploadFileAction failed for id={action_id}, file_path={file_path}: could not get file.",
            user_message=f"Unable to get file: {file_path} for upload. Please check that it exists at the right path.",
            agent_message=f"The file: {file_path} could not be found. Hint: find a different file to use for the UploadFileAction.",
        )


class NoStorageObjectProvidedError(NotteBaseError):
    def __init__(self, action_name: str) -> None:
        super().__init__(
            dev_message=f"Cannot execute {action_name} because no `storage` object was provided to the session.",
            user_message=f"Cannot execute {action_name} because no `storage` object was provided to the session.",
            agent_message=f"Cannot execute {action_name} because no `storage` object was provided to the session.",
        )


class FailedToDownloadFileError(NotteBaseError):
    def __init__(self) -> None:
        super().__init__(
            dev_message="File download succeeded in session, but upload to persistent storage failed.",
            user_message="Download could not be completed due to internal error!",
            agent_message="An internal error prevented the download from succeeding. Stop running and notify that the operation failed.",
        )


# #######################################################
# ################## Captcha errors #####################
# #######################################################


class CaptchaSolverNotAvailableError(NotteBaseError):
    message: str = "Captcha solving isn't implemented in the open repo. Please use the sdk client: `client.Session(solve_captchas=True)` to enable captcha solving."

    def __init__(self) -> None:
        super().__init__(
            dev_message=self.message,
            user_message=self.message,
            agent_message=self.message,
        )


class NoToolProvidedError(NotteBaseError):
    def __init__(self, action: ToolAction) -> None:
        msg = f"No provided tool is able to execute the action: {action.name()}. You should use `notte.Session(tools=[...])` to add tools to the session."
        super().__init__(
            dev_message=msg,
            user_message=msg,
            agent_message=msg,
        )
