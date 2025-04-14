from collections.abc import Awaitable
from typing import Callable, Generic, TypeVar, final

from notte_core.errors.base import NotteBaseError
from notte_core.errors.provider import RateLimitError
from pydantic import BaseModel
from pydantic_core import ValidationError

S = TypeVar("S")  # Source type
T = TypeVar("T")  # Target type
F = TypeVar("F")  # Failure type


class ExecutionStatus(BaseModel, Generic[S, T]):
    input: S
    output: T | None
    success: bool
    message: str
    should_rerun_step_agent: bool = False
    

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
class SafeActionExecutor(Generic[S, T, F]):
    def __init__(
        self,
        func: Callable[[S], Awaitable[T]],
        on_failure_handlers: dict[type[F], Callable[[F], Awaitable]] | None = None,
        precheck_func: Callable[[S], None] | None = None,
        max_consecutive_failures: int = 3,
        raise_on_failure: bool = True,
    ) -> None:
        self.func = func
        self.precheck_func = precheck_func
        self.max_consecutive_failures = max_consecutive_failures
        self.consecutive_failures = 0
        self.raise_on_failure = raise_on_failure
        self.on_failure_handlers = on_failure_handlers if on_failure_handlers is not None else {}

    def reset(self) -> None:
        self.consecutive_failures = 0

    def on_failure(self, input_data: S, error_msg: str, e: Exception) -> ExecutionStatus[S, T]:
        self.consecutive_failures += 1
                
        handler = self.on_failure_handlers.get(type(e))
        if handler is not None and callable(handler):
            handler(e)
        
        if self.consecutive_failures >= self.max_consecutive_failures:
            raise MaxConsecutiveFailuresError(self.max_consecutive_failures) from e
        if self.raise_on_failure:
            raise StepExecutionFailure(error_msg) from e
        return ExecutionStatus(
            input=input_data,
            output=None,
            success=False,
            message=error_msg,
            should_rerun_step_agent=True if self.consecutive_failures <= self.max_consecutive_failures else False,
        )
    
    

    async def execute(self, input_data: S) -> ExecutionStatus[S, T]:
        try:
            if self.precheck_func is not None:
                self.precheck_func(input_data)
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
