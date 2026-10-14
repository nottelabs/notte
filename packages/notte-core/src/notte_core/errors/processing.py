from notte_core.errors.base import NotteBaseError


class SnapshotProcessingError(NotteBaseError):
    """
    Error raised when there is an issue processing a snapshot.
    All of these issues should, in theory, not occur but, in practice,
    since Notte is still in development, they are likely to happen.

    Most of them should be fixed by updating the preprocessing pipeline.
    """

    def __init__(self, url: str | None, dev_message: str) -> None:
        url_str = f": {url}" if url else ""
        super().__init__(
            dev_message=dev_message,
            user_message=f"Sorry, Notte is not yet able to process this website{url_str}.",
            agent_message="Sorry, this action is not yet supported. Hint: try another action.",
            should_notify_team=True,
        )


class InvalidInternalCheckError(SnapshotProcessingError):
    """
    Multiple internal checks are performed when the snapshot is processed.
    This error is raised when one of the internal checks fails.

    To fix this error, developers should:
    - Undersand with the internal check failed
    - Decide wether the internal check is simply not relevant for the given snapshot
    - Or if custom processing need to be handled by the developer for the given snapshot
    """

    def __init__(self, url: str | None, check: str, dev_advice: str) -> None:
        super().__init__(
            dev_message=f"Internal check '{check}' failed during snapshot processing. Advice to resolve: {dev_advice}",
            url=url,
        )


class InvalidPlaceholderError(NotteBaseError):
    def __init__(self, placeholder: str) -> None:
        dev_message = f"The placeholder {placeholder} is not handled by your current vault."
        agent_message = f"Could not perform action with value {placeholder}. Try picking a different value"
        user_message = "Unexpected error while requesting credentials from vault"

        super().__init__(
            agent_message=agent_message,
            user_message=user_message,
            dev_message=dev_message,
        )


class ScrapeFailedError(NotteBaseError):
    def __init__(self, error_message: str) -> None:
        super().__init__(
            dev_message=f"Structured data extraction failed: {error_message}",
            user_message=f"Failed to extract structured data: {error_message}",
            agent_message=f"Structured data extraction failed: {error_message}. Hint: verify the page contains the expected data or adjust your instructions.",
            should_retry_later=True,
        )
