import asyncio
from abc import ABC, abstractmethod
from typing import Unpack

from notte_browser.session import NotteSession
from notte_sdk.types import AgentRunRequestDict

from notte_agent.common.types import AgentResponse


class BaseAgent(ABC):
    def __init__(self, session: NotteSession):
        self.session: NotteSession = session

    @abstractmethod
    async def arun(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        pass

    def run(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        return asyncio.run(self.arun(**data))
