import asyncio
from collections.abc import Callable

from notte_browser.session import NotteSession
from notte_core.credentials.base import BaseVault
from notte_core.llms.engine import LlmModel
from notte_sdk.types import DEFAULT_MAX_NB_STEPS, AgentCreateRequest

from notte_agent.common.base import BaseAgent
from notte_agent.common.notifier import BaseNotifier, NotifierAgent
from notte_agent.common.types import AgentResponse
from notte_agent.falco.agent import FalcoAgent, FalcoAgentConfig
from notte_agent.falco.types import StepAgentOutput


class Agent:
    def __init__(
        self,
        headless: bool = False,
        reasoning_model: LlmModel = LlmModel.default(),  # type: ignore[reportCallInDefaultInitializer]
        max_steps: int = DEFAULT_MAX_NB_STEPS,
        use_vision: bool = True,
        # /!\ web security is disabled by default to increase agent performance
        # turn it off if you need to input confidential information on trajectories
        web_security: bool = False,
        chrome_args: list[str] | None = None,
        vault: BaseVault | None = None,
        notifier: BaseNotifier | None = None,
        session: NotteSession | None = None,
    ):
        # just validate the request to create type dependency
        _ = AgentCreateRequest(
            reasoning_model=reasoning_model,
            use_vision=use_vision,
            max_steps=max_steps,
            vault_id=None,
        )
        self.config: FalcoAgentConfig = (
            FalcoAgentConfig()
            .use_vision(use_vision)
            .model(reasoning_model, deep=True)
            .map_session(
                lambda session: (
                    session.agent_mode()
                    .steps(max_steps)
                    .headless(headless)
                    .web_security(web_security)
                    .set_chrome_args(chrome_args)
                )
            )
        )
        self.vault: BaseVault | None = vault
        self.notifier: BaseNotifier | None = notifier
        self.session: NotteSession = session or NotteSession(config=self.config.session)
        self.auto_manage_session: bool = session is None

    def create_agent(
        self,
        step_callback: Callable[[str, StepAgentOutput], None] | None = None,
    ) -> BaseAgent:
        agent = FalcoAgent(
            config=self.config,
            vault=self.vault,
            window=self.session.window,
            step_callback=step_callback,
        )
        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return agent

    async def arun(self, task: str, url: str | None = None) -> AgentResponse:
        try:
            if self.auto_manage_session:
                # need to start session before running the agent
                await self.session.astart()

            agent = self.create_agent()

            return await agent.run(task, url=url)
        finally:
            if self.auto_manage_session:
                await self.session.astop()

    def run(self, task: str, url: str | None = None) -> AgentResponse:
        return asyncio.run(self.arun(task, url=url))
