from notte_core.errors.base import NotteBaseError


class ActionError(NotteBaseError):
    """Base class for Action related errors."""

    pass


class ActionExecutionError(ActionError):
    def __init__(self, action_id: str, url: str, reason: str | None = None) -> None:
        super().__init__(
            dev_message=f"Failed to execute action: {action_id} on {url}. Reason: {reason or 'unknown'}",
            user_message="Sorry, this action cannot be executed at the moment.",
            agent_message=(
                f"Failed to execute action: {action_id} on {url}. Reason: {reason or 'unknown'}. "
                "Hint: check if the action is valid and try again. Otherwise, try another action."
            ),
            should_retry_later=True,
            should_notify_team=True,
        )


class NotEnoughActionsListedError(ActionError):
    def __init__(self, n_trials: int, n_actions: int, threshold: float) -> None:
        super().__init__(
            dev_message=(
                f"Not enough actions listed after {n_trials} trials"
                f"(termination threshold: {threshold}, for {n_actions} to be listed). "
                "You can retry or reduce `min_nb_actions` or `max_nb_actions`"
            ),
            user_message="Notte failed to list enough actions. This often happens on large web pages.",
            agent_message=(
                "Notte failed to list enough actions. This often happens on large web pages. "
                "You should terminate the current session or try another URL."
            ),
            should_retry_later=True,
            should_notify_team=True,
        )


class InvalidActionError(ActionError):
    def __init__(self, action_id: str, reason: str) -> None:
        super().__init__(
            dev_message=f"Action with id '{action_id}' is invalid: {reason}.",
            user_message=f"Action with id '{action_id}' is invalid. Please provide a valid action and try again.",
            agent_message=(
                f"Action with id '{action_id}' is invalid. Hint: provide a valid action and try again. "
                "Otherwise, try another action."
            ),
        )


class InputActionShouldHaveOneParameterError(InvalidActionError):
    def __init__(self, action_id: str) -> None:
        super().__init__(
            action_id=action_id,
            reason="Input actions require exactly one parameter",
        )


class NoCredentialsFoundError(ActionError):
    def __init__(self, url: str) -> None:
        msg = (
            f"No credentials found in the vault for url={url}. Please add valid credentials in the vault and try again."
        )
        super().__init__(
            dev_message=msg,
            user_message=msg,
            agent_message=msg,
        )
