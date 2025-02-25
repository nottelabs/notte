from requests import Response

from notte.errors.base import NotteBaseError


class NotteAPIError(NotteBaseError):
    def __init__(self, path: str, response: Response) -> None:
        super().__init__(
            dev_message=f"Request to `{path}` failed with status code {response.status_code}: {response.json()}",
            user_message="An unexpected error occurred during the request to the Notte API.",
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
