from notte.errors.base import NotteBaseError


class BrowserError(NotteBaseError):
    """Base class for Browser related errors."""

    pass


class PageLoadingError(BrowserError):

    def __init__(self, url: str) -> None:
        super().__init__(
            dev_message=f"Failed to load page from {url}",
            user_message="Failed to load page from the given URL. Check if the URL is reachable.",
            should_retry_later=True,
        )


class InvalidURLError(BrowserError):
    def __init__(
        self,
        url: str,
    ) -> None:
        super().__init__(
            dev_message=(
                (f"Invalid URL: {url}. Check if the URL is reachable. " "URLs should start with https:// or http://. ")
            ),
            user_message=(
                (
                    "Impossible to access the given URL. Check if the URL is reachable. "
                    "Remember that URLs should start with https:// or http://"
                )
            ),
            should_retry_later=False,
        )


class SSLError(BrowserError):
    def __init__(
        self,
        url: str,
    ) -> None:
        super().__init__(
            dev_message=f"SSL certificate verification failed for {url}",
            user_message="SSL certificate verification failed. Please try again later.",
            should_retry_later=False,
        )


class BrowserNotStartedError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message=(
                (
                    "Browser not started. You should use `await browser.start()` to start a new session "
                    "(or `await env.start()`)."
                )
            ),
            user_message=(("Session not started. Please start a new session to continue.")),
            should_retry_later=False,
        )


class BrowserExpiredError(BrowserError):
    def __init__(self) -> None:
        super().__init__(
            dev_message=(
                "Browser or context expired or closed. You should use `await browser.start()` to start a new session."
            ),
            user_message="Session expired or closed. Create a new session to continue.",
            should_retry_later=False,
        )


class EmptyPageContentError(BrowserError):
    def __init__(self, url: str, nb_retries: int) -> None:
        super().__init__(
            dev_message=(
                (
                    f"Browser snapshot failed after {nb_retries} retries to get a non-empty web page for: {url}. "
                    "Notte cannot continue without a valid page. Try to increase the short waiting time in "
                    "`notte.browser.driver.py`."
                )
            ),
            user_message=(("Webpage appears to be empty and cannot be processed.")),
            should_retry_later=True,
            should_notify_team=True,
        )


class UnexpectedBrowserError(BrowserError):
    def __init__(self, url: str) -> None:
        super().__init__(
            dev_message=f"Unexpected error detected: {url}. Notte cannot continue without a valid page. ",
            user_message="An unexpected error occurred within the browser session.",
            should_retry_later=True,
            should_notify_team=True,
        )


class BrowserResourceNotFoundError(BrowserError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=message,
            user_message="The requested browser resource was not found. Please start a new session.",
            should_retry_later=False,
        )


class BrowserResourceLimitError(BrowserError):
    def __init__(self, message: str) -> None:
        super().__init__(
            dev_message=message,
            user_message="Sorry, we are experiencing high traffic at the moment. Try again later with a new session.",
            should_retry_later=False,
        )
