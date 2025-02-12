from abc import ABC, abstractmethod

from litellm import AllMessageValues
from pydantic import BaseModel

from notte.env import TrajectoryStep


class AgentOutput(BaseModel):
    answer: str
    success: bool
    trajectory: list[TrajectoryStep]
    messages: list[AllMessageValues] | None = None


class BaseAgent(ABC):

    @abstractmethod
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        pass
