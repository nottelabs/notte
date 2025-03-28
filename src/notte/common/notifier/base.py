from abc import ABC, abstractmethod

from typing_extensions import override

from notte.common.agent.base import BaseAgent
from notte.common.agent.types import AgentResponse


class BaseNotifier(ABC):
    """Base class for notification implementations."""

    @abstractmethod
    async def send_message(self, text: str) -> None:
        """Send a message using the specific notification service."""
        pass

    async def notify(self, task: str, result: AgentResponse) -> None:
        """Send a notification about the task result.

        Args:
            task: The task description
            result: The agent's response to be sent
        """
        message = f"""
Notte Agent Report 🌙

Task Details:
-------------
Task: {task}
Execution Time: {round(result.duration_in_s, 2)} seconds
Status: {"✅ Success" if result.success else "❌ Failed"}


Agent Response:
--------------
{result.answer}

Powered by Notte 🌒"""
        await self.send_message(text=message)


class NotifierAgent(BaseAgent):
    """Agent wrapper that sends notifications after task completion."""

    def __init__(self, agent: BaseAgent, notifier: BaseNotifier):
        self.agent: BaseAgent = agent
        self.notifier: BaseNotifier = notifier

    @override
    async def run(self, task: str, url: str | None = None) -> AgentResponse:
        """Run the agent and send notification about the result."""
        result = await self.agent.run(task, url)
        await self.notifier.notify(task, result)
        return result
