import asyncio
from collections.abc import Callable
from enum import StrEnum
from typing import Unpack

from notte_browser.session import NotteSession
from notte_core.credentials.base import BaseVault
from notte_sdk.types import AgentCreateRequestDict

from notte_agent.common.base import BaseAgent
from notte_agent.common.notifier import BaseNotifier, NotifierAgent
from notte_agent.common.types import AgentResponse
from notte_agent.falco.agent import FalcoAgent
from notte_agent.falco.types import StepAgentOutput
from notte_agent.gufo.agent import GufoAgent


class AgentType(StrEnum):
    FALCO = "falco"
    GUFO = "gufo"


class Agent:
    def __init__(
        self,
        headless: bool = False,
        vault: BaseVault | None = None,
        notifier: BaseNotifier | None = None,
        session: NotteSession | None = None,
        agent_type: AgentType = AgentType.FALCO,
        **data: Unpack[AgentCreateRequestDict],
    ):
        # just validate the request to create type dependency
        self.data: AgentCreateRequestDict = data
        self.vault: BaseVault | None = vault
        self.notifier: BaseNotifier | None = notifier
        self.auto_close_session: bool = session is None
        self.session: NotteSession = session or NotteSession(headless=headless)
        self.agent_type: AgentType = agent_type

    async def create_agent(
        self,
        step_callback: Callable[[str, StepAgentOutput], None] | None = None,
    ) -> BaseAgent:
        match self.agent_type:
            case AgentType.FALCO:
                agent = FalcoAgent(
                    vault=self.vault,
                    window=self.session.window,
                    step_callback=step_callback,
                    **self.data,
                )
            case AgentType.GUFO:
                agent = GufoAgent(
                    vault=self.vault,
                    window=self.session.window,
                    # TODO: enable this
                    # step_callback=step_callback,
                    **self.data,
                )
        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return agent

    async def arun(self, task: str, url: str | None = None) -> AgentResponse:
        try:
            if self.auto_close_session:
                await self.session.start()
            agent = await self.create_agent()

            return await agent.run(task, url=url)
        finally:
            if self.auto_close_session:
                await self.session.stop()

    def run(self, task: str, url: str | None = None) -> AgentResponse:
        return asyncio.run(self.arun(task, url=url))
