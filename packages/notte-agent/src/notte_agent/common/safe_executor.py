from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar, final

from notte_core.errors.base import NotteBaseError
from notte_core.errors.provider import RateLimitError
from pydantic import BaseModel
from pydantic_core import ValidationError

S = TypeVar("S")  # Source type
T = TypeVar("T")  # Target type


class ExecutionStatus(BaseModel, Generic[S, T]):
    input: S
    output: T | None
    success: bool
    message: str

    def get(self) -> T:
        if self.output is None or not self.success:
            raise ValueError(f"Execution failed with message: {self.message}")
        return self.output


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
class SafeActionExecutor(Generic[S, T]):
    def __init__(
        self,
        func: Callable[[S], Awaitable[T]],
        max_consecutive_failures: int = 3,
        raise_on_failure: bool = True,
    ) -> None:
        self.func = func
        self.max_consecutive_failures = max_consecutive_failures
        self.consecutive_failures = 0
        self.raise_on_failure = raise_on_failure

    def reset(self) -> None:
        self.consecutive_failures = 0

    def on_failure(self, input_data: S, error_msg: str, e: Exception) -> ExecutionStatus[S, T]:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures:
            raise MaxConsecutiveFailuresError(self.max_consecutive_failures) from e
        if self.raise_on_failure:
            raise StepExecutionFailure(error_msg) from e
        return ExecutionStatus(
            input=input_data,
            output=None,
            success=False,
            message=error_msg,
        )

    async def execute(self, input_data: S, err: NotteBaseError | None = None) -> ExecutionStatus[S, T]:
        try:
            if err is not None:
                raise err

            result = await self.func(input_data)
            self.consecutive_failures = 0
            return ExecutionStatus(
                input=input_data,
                success=True,
                output=result,
                message=f"Successfully executed action with input: {input_data}",
            )
        except RateLimitError as e:
            return self.on_failure(input_data, "Rate limit reached. Waiting before retry.", e)
        except NotteBaseError as e:
            # When raise_on_failure is True, we use the dev message to give more details to the user
            msg = e.dev_message if self.raise_on_failure else e.agent_message
            return self.on_failure(input_data, msg, e)
        except ValidationError as e:
            return self.on_failure(
                input_data,
                (
                    "JSON Schema Validation error: The output format is invalid. "
                    f"Please ensure your response follows the expected schema. Details: {str(e)}"
                ),
                e,
            )
        except Exception as e:
            return self.on_failure(input_data, f"An unexpected error occurred: {e}", e)
