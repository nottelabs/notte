import asyncio
from collections.abc import Callable
from enum import StrEnum
from typing import Unpack

from notte_browser.session import NotteSession
from notte_core.common.config import config
from notte_core.common.notifier import BaseNotifier
from notte_core.credentials.base import BaseVault
from notte_sdk.types import AgentCreateRequestDict, AgentRunRequest, AgentRunRequestDict

from notte_agent.common.base import BaseAgent
from notte_agent.common.notifier import NotifierAgent
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
        headless: bool = config.headless,
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
        self.session: NotteSession = session or NotteSession(headless=headless)
        self.auto_manage_session: bool = session is None
        self.agent_type: AgentType = agent_type

    def create_agent(
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
                    # TODO: fix this
                    # step_callback=step_callback,
                    **self.data,
                )
        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return agent

    async def arun(self, **kwargs: Unpack[AgentRunRequestDict]) -> AgentResponse:
        try:
            if self.auto_manage_session:
                # need to start session before running the agent
                await self.session.astart()
            agent = self.create_agent()
            # validate args
            res = AgentRunRequest.model_validate(kwargs)
            return await agent.run(**res.model_dump())
        except Exception as e:
            raise e
        finally:
            if self.auto_manage_session:
                await self.session.astop()

    def run(self, **kwargs: Unpack[AgentRunRequestDict]) -> AgentResponse:
        try:
            if self.auto_manage_session:
                # need to start session before running the agent
                self.session.start()
            agent = self.create_agent()
            # validate args
            res = AgentRunRequest.model_validate(kwargs)
            return asyncio.run(agent.run(**res.model_dump()))
        except Exception as e:
            raise e
        finally:
            if self.auto_manage_session:
                self.session.stop()
