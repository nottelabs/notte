from notte_core.errors.base import NotteBaseError


class StepExecutionFailure(NotteBaseError):
    def __init__(self, message: str):
        super().__init__(
            user_message=message,
            agent_message=message,
            dev_message=message,
        )


class MaxConsecutiveFailuresError(NotteBaseError):
    def __init__(self, max_failures: int):
        self.max_failures: int = max_failures
        message = f"Max consecutive failures reached in a single step: {max_failures}."
        super().__init__(
            user_message=message,
            agent_message=message,
            dev_message=message,
        )
