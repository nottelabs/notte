from abc import ABC, abstractmethod

from notte.common.agent.base import BaseAgent
from notte.common.agent.types import AgentResponse


class BaseNotifier(ABC):
    """Base class for notification implementations."""

    @abstractmethod
    async def notify(self, task: str, result: AgentResponse) -> None:
        """Send a notification about the task result."""
        pass


class NotifierAgent:
    """Agent wrapper that sends notifications after task completion."""

    def __init__(self, agent: BaseAgent, notifier: BaseNotifier):
        self.agent: BaseAgent = agent
        self.notifier: BaseNotifier = notifier

    async def run(self, task: str, url: str | None = None) -> AgentResponse:
        """Run the agent and send notification about the result."""
        result = await self.agent.run(task, url)
        await self.notifier.notify(task, result)
        return result
