from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel


class EvalEnum(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class EvaluationResponse(BaseModel):
    class Config:
        frozen: bool = True

    eval: EvalEnum
    reason: str


class Evaluator(BaseModel, ABC):  # type: ignore[reportUnsafeMultipleInheritance]
    class Config:
        frozen: bool = True

    @abstractmethod
    async def eval(
        self,
        answer: str,
        task: str,
        screenshots: list[str],
    ) -> EvaluationResponse: ...
