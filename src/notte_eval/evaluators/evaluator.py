from abc import abstractmethod
from enum import StrEnum

from pydantic import BaseModel


class EvalEnum(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class EvaluationResponse(BaseModel):
    class Config:
        frozen = True

    eval: EvalEnum
    reason: str


class Evaluator(BaseModel):
    class Config:
        frozen = True

    @abstractmethod
    async def eval(
        self,
        answer: str,
        task: str,
        screenshots: list[str],
    ) -> EvaluationResponse: ...
