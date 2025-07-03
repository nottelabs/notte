from enum import StrEnum
from typing import Unpack

from notte_browser.session import NotteSession
from notte_browser.tools.base import BaseTool, PersonaTool
from notte_core.common.notifier import BaseNotifier
from notte_core.credentials.base import BaseVault
from notte_sdk.endpoints.personas import Persona
from notte_sdk.types import AgentCreateRequestDict, AgentRunRequest, AgentRunRequestDict
from typing_extensions import override

from notte_agent.common.base import BaseAgent
from notte_agent.common.notifier import NotifierAgent
from notte_agent.common.types import AgentResponse
from notte_agent.falco.agent import FalcoAgent
from notte_agent.gufo.agent import GufoAgent


class AgentType(StrEnum):
    FALCO = "falco"
    GUFO = "gufo"


class Agent(BaseAgent):
    def __init__(
        self,
        session: NotteSession,
        vault: BaseVault | None = None,
        persona: Persona | None = None,
        notifier: BaseNotifier | None = None,
        agent_type: AgentType = AgentType.FALCO,
        **data: Unpack[AgentCreateRequestDict],
    ):
        super().__init__(session=session)
        # just validate the request to create type dependency
        self.data: AgentCreateRequestDict = data
        self.vault: BaseVault | None = vault
        self.notifier: BaseNotifier | None = notifier
        self.session: NotteSession = session
        self.agent_type: AgentType = agent_type

        self.tools: list[BaseTool] = self.session.tools
        if persona is not None:
            self.vault = self.vault or (persona.vault if persona.has_vault else None)
            self.tools.append(PersonaTool(persona))

    def create_agent(
        self,
    ) -> BaseAgent:
        match self.agent_type:
            case AgentType.FALCO:
                agent = FalcoAgent(
                    vault=self.vault,
                    session=self.session,
                    tools=self.tools,
                    **self.data,
                )
            case AgentType.GUFO:
                agent = GufoAgent(
                    vault=self.vault,
                    session=self.session,
                    **self.data,
                )

        # agent.session.start_from(self.session)

        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return agent

    @override
    async def arun(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        agent = self.create_agent()
        # validate args
        res = AgentRunRequest.model_validate(data)
        return await agent.arun(**res.model_dump())
