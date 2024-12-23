from abc import ABC, abstractmethod
from dataclasses import dataclass

from notte.browser.snapshot import BrowserSnapshot


@dataclass
class AgentOutput:
    answer: str
    success: bool
    snapshot: BrowserSnapshot | None = None


class BaseAgent(ABC):

    @abstractmethod
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        pass
