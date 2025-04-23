from abc import ABC, abstractmethod

from notte_browser.session import NotteSession

from notte_agent.common.types import AgentResponse


class BaseAgent(ABC):
    def __init__(self, session: NotteSession):
        self.session: NotteSession = session

    @abstractmethod
    async def run(self, task: str, url: str | None = None) -> AgentResponse:
        pass
