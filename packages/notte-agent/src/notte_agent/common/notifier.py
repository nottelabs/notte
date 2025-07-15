from typing import Any, Unpack

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

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped agent if not found on this instance."""
        return getattr(self.agent, name)

    @override
    async def run(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        """Run the agent and send notification about the result."""
        result = await self.agent.run(**data)
        self.notifier.notify(data["task"], result)  # pyright: ignore [reportArgumentType]
        return result
