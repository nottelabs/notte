from abc import ABC, abstractmethod
from dataclasses import dataclass

from litellm import Message

from notte.env import TrajectoryStep


@dataclass
class AgentOutput:
    answer: str
    success: bool
    trajectory: list[TrajectoryStep]
    messages: list[Message] | None = None


class BaseAgent(ABC):

    @abstractmethod
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        pass
