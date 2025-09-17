from enum import StrEnum
from typing import Unpack

from notte_browser.session import NotteSession
from notte_browser.tools.base import BaseTool, PersonaTool
from notte_core.common.notifier import BaseNotifier
from notte_core.credentials.base import BaseVault
from notte_core.trajectory import Trajectory
from notte_sdk.endpoints.personas import BasePersona
from notte_sdk.types import AgentCreateRequestDict, AgentRunRequest, AgentRunRequestDict
from typing_extensions import override

from notte_agent.agent import NotteAgent
from notte_agent.common.base import BaseAgent
from notte_agent.common.notifier import NotifierAgent
from notte_agent.common.types import AgentResponse
from notte_agent.falco.agent import FalcoAgent
from notte_agent.gufo.agent import GufoAgent


class AgentType(StrEnum):
    FALCO = "falco"
    GUFO = "gufo"

    def get_agent_class(self) -> type[FalcoAgent | GufoAgent]:
        match self:
            case AgentType.FALCO:
                return FalcoAgent
            case AgentType.GUFO:
                return GufoAgent


class Agent(BaseAgent):
    def __init__(
        self,
        session: NotteSession,
        vault: BaseVault | None = None,
        persona: BasePersona | None = None,
        notifier: BaseNotifier | None = None,
        agent_type: AgentType = AgentType.FALCO,
        trajectory: Trajectory | None = None,
        **data: Unpack[AgentCreateRequestDict],
    ):
        super().__init__(session=session)
        # just validate the request to create type dependency
        self.data: AgentCreateRequestDict = data
        self.vault: BaseVault | None = vault
        self.notifier: BaseNotifier | None = notifier
        self.session: NotteSession = session
        self.agent_type: AgentType = agent_type
        self.trajectory: Trajectory | None = trajectory or session.trajectory.view()

        self.tools: list[BaseTool] = self.session.tools
        if persona is not None:
            self.vault = self.vault or (persona.vault if persona.has_vault else None)
            self.tools.append(PersonaTool(persona))

    def create_agent(
        self,
    ) -> BaseAgent:
        AgentClass = self.agent_type.get_agent_class()
        agent = AgentClass(
            vault=self.vault,
            session=self.session,
            tools=self.tools,
            trajectory=self.trajectory,
            **self.data,
        )

        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return agent

    @override
    async def arun(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        agent = self.create_agent()
        # validate args
        res = AgentRunRequest.model_validate(data)
        agent_res = await agent.arun(**res.model_dump())
        if isinstance(agent, NotteAgent):
            self.trajectory = agent.trajectory
        return agent_res
