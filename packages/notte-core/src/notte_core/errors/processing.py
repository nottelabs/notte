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


class InconsistentInteractionsNodesInAxTrees(InvalidInternalCheckError):
    def __init__(self, check: str) -> None:
        super().__init__(
            check=check,
            dev_advice=(
                "There are inconsistencies between interaction nodes in two ax trees, this should not happen. "
                "You should investigate the reason why. You could first try to set `raise_error=False` to "
                "get more low level information. You should also try to print the ax trees to see where the "
                "issue is coming from."
            ),
            url=None,
        )


class NodeFilteringResultsInEmptyGraph(SnapshotProcessingError):
    """
    Error raised when node filtering results in an empty graph.
    """

    def __init__(self, url: str | None, operation: str = "filtering") -> None:
        super().__init__(
            dev_message=(
                f"Operation '{operation}' resulted in an empty graph. Notte always expect a non-empty graph. "
                "Please check the `pruning.py` file or `subtree_without` method for more information."
            ),
            url=url,
        )


class InvalidA11yTreeType(InvalidInternalCheckError):
    def __init__(self, type: str) -> None:
        super().__init__(
            check=f"Unknown a11y tree type {type}. Valid types are: 'processed', 'simple', 'raw'.",
            dev_advice="This should not happen. Someone proably added a new type without updating properly the code.",
            url=None,
        )


class InvalidA11yChildrenError(InvalidInternalCheckError):
    def __init__(self, check: str, nb_children: int) -> None:
        super().__init__(
            check=f"{check}. Note that the number of children is {nb_children}.",
            dev_advice="Some assupmtions are not met. You should check the code to see why this is happening.",
            url=None,
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


class CredentialFieldValidationError(NotteBaseError):
    """Raised when a sentinel placeholder is used to fill an element that fails the credential
    field's element-validation check (e.g. a password placeholder targeted at a non-password
    element such as a <label>). Without this error the substitution would silently no-op and the
    literal placeholder string would be typed into the field."""

    def __init__(self, placeholder: str, cred_key: str, attrs: object) -> None:
        dev_message = (
            f"Sentinel placeholder {placeholder!r} for credential field {cred_key!r} was supplied, "
            f"but the targeted element failed validate_element. Element attrs: {attrs!r}. "
            f"Common cause: the action targeted a wrapper (e.g. <label>) instead of the actual "
            f"<input>. Re-target the input element directly."
        )
        agent_message = (
            f"Could not fill credential {cred_key!r}: targeted element is not a valid {cred_key!r} input. "
            f"Re-locate the actual input field and retry."
        )
        user_message = "Credential placeholder used on an element that is not a valid target for that field."
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
