from abc import ABC, abstractmethod

from notte_browser.env import NotteEnv

from notte_agent.common.types import AgentResponse


class BaseAgent(ABC):
    def __init__(self, env: NotteEnv):
        self.env: NotteEnv = env

    @abstractmethod
    async def run(self, task: str, url: str | None = None) -> AgentResponse:
        pass
