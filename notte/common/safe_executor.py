from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, final

from pydantic_core import ValidationError

from notte.errors.base import NotteBaseError
from notte.errors.provider import RateLimitError

S = TypeVar("S")  # Source type
T = TypeVar("T")  # Target type


@dataclass
class ExecutionStatus(Generic[S, T]):
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
        super().__init__(message, user_message="")


class MaxConsecutiveFailuresError(NotteBaseError):
    def __init__(self, max_failures: int):
        self.max_failures: int = max_failures
        super().__init__(f"Max consecutive failures reached in a single step: {max_failures}", user_message="")


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

    async def execute(self, input_data: S) -> ExecutionStatus[S, T]:
        try:
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
            return self.on_failure(
                input_data, f"Failure during action execution with error: {e.dev_message} : {e.user_message}", e
            )
        except ValidationError as e:
            return self.on_failure(
                input_data,
                (
                    f"JSON Schema Validation error: The output format is invalid. "
                    f"Please ensure your response follows the expected schema. Details: {str(e)}"
                ),
                e,
            )
        except Exception as e:
            return self.on_failure(input_data, f"An unexpected error occurred: {e}", e)
