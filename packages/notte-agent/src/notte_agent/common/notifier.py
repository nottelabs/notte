from typing import Unpack

from notte_core.common.notifier import BaseNotifier
from notte_sdk.types import AgentRunRequestDict
from typing_extensions import override

from notte_agent.common.base import BaseAgent
from notte_agent.common.types import AgentResponse


class NotifierAgent(BaseAgent):
    """Agent wrapper that sends notifications after task completion."""

    def __init__(self, agent: BaseAgent, notifier: BaseNotifier):
        super().__init__(session=agent.session)
        self.agent: BaseAgent = agent
        self.notifier: BaseNotifier = notifier

    @override
    async def run(self, **kwargs: Unpack[AgentRunRequestDict]) -> AgentResponse:
        task = kwargs.get("task")
        """Run the agent and send notification about the result."""
        result = await self.agent.run(**kwargs)
        self.notifier.notify(task, result)  # pyright: ignore [reportArgumentType]
        return result
