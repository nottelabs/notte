import asyncio
from collections.abc import Callable
from enum import StrEnum
from typing import Unpack

from notte_browser.session import NotteSession
from notte_core.agent_types import AgentStepResponse
from notte_core.common.notifier import BaseNotifier
from notte_core.credentials.base import BaseVault
from notte_sdk.types import AgentCreateRequestDict, AgentRunRequest, AgentRunRequestDict

from notte_agent.common.base import BaseAgent
from notte_agent.common.notifier import NotifierAgent
from notte_agent.common.types import AgentResponse
from notte_agent.falco.agent import FalcoAgent
from notte_agent.gufo.agent import GufoAgent


class AgentType(StrEnum):
    FALCO = "falco"
    GUFO = "gufo"


class Agent:
    def __init__(
        self,
        session: NotteSession,
        vault: BaseVault | None = None,
        notifier: BaseNotifier | None = None,
        agent_type: AgentType = AgentType.FALCO,
        **data: Unpack[AgentCreateRequestDict],
    ):
        # just validate the request to create type dependency
        self.data: AgentCreateRequestDict = data
        self.vault: BaseVault | None = vault
        self.notifier: BaseNotifier | None = notifier
        self.session: NotteSession = session
        self.agent_type: AgentType = agent_type

    def create_agent(
        self,
        step_callback: Callable[[AgentStepResponse], None] | None = None,
    ) -> BaseAgent:
        match self.agent_type:
            case AgentType.FALCO:
                agent = FalcoAgent(
                    vault=self.vault,
                    window=self.session.window,
                    storage=self.session.storage,
                    step_callback=step_callback,
                    **self.data,
                )
            case AgentType.GUFO:
                agent = GufoAgent(
                    vault=self.vault,
                    window=self.session.window,
                    # TODO: fix this
                    # step_callback=step_callback,
                    **self.data,
                )
        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return agent

    async def arun(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        agent = self.create_agent()
        # validate args
        res = AgentRunRequest.model_validate(data)
        return await agent.run(**res.model_dump())

    def run(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        return asyncio.run(self.arun(**data))
