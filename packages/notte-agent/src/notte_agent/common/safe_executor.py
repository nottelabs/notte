from typing import final

from notte_browser.session import NotteSession, SessionTrajectoryStep
from notte_core.actions import BaseAction
from notte_core.browser.observation import StepResult
from notte_core.common.config import config
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


@final
class SafeActionExecutor:
    def __init__(
        self,
        session: NotteSession,
        max_consecutive_failures: int = config.max_consecutive_failures,
    ) -> None:
        self.session = session
        self.max_consecutive_failures = max_consecutive_failures
        self.consecutive_failures = 0

    def reset(self) -> None:
        self.consecutive_failures = 0

    async def fail(self, action: BaseAction, message: str, exception: Exception | None = None) -> SessionTrajectoryStep:
        _ = await self.session.astep(action)
        obs = await self.session.aobserve()
        return SessionTrajectoryStep(
            action=action,
            obs=obs,
            result=StepResult(success=False, message=message, exception=exception),
        )

    async def execute(self, action: BaseAction) -> SessionTrajectoryStep:
        result = await self.session.astep(action)
        if result.success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_consecutive_failures:
                # max consecutive failures reached, raise an exception
                if result.exception is None:
                    result.exception = ValueError(result.message)
                raise MaxConsecutiveFailuresError(self.max_consecutive_failures) from result.exception

        obs = await self.session.aobserve()
        return SessionTrajectoryStep(
            action=action,
            result=result,
            obs=obs,
        )
