from abc import ABC, abstractmethod

from notte.common.agent.types import AgentResponse


class BaseAgent(ABC):
    @abstractmethod
    async def run(self, task: str, url: str | None = None) -> AgentResponse:
        pass
