from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, final

from notte.errors.base import NotteBaseError

S = TypeVar("S")  # Source type
T = TypeVar("T")  # Target type


@dataclass
class ExecutionStatus(Generic[T]):
    status: bool
    output: T | None
    message: str


@final
class SafeActionExecutor(Generic[S, T]):
    def __init__(self, func: Callable[[S], T]) -> None:
        self.func = func

    def execute(self, input_data: S) -> ExecutionStatus[T]:
        try:
            result = self.func(input_data)
            return ExecutionStatus(
                status=True, output=result, message=f"Successfully executed action with input: {input_data}"
            )
        except NotteBaseError as e:
            return ExecutionStatus(
                status=False, output=None, message=f"Failure during action execution with error: {e.dev_message}."
            )
