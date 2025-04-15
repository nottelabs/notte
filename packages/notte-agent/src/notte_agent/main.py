import asyncio
from collections.abc import Callable

from notte_browser.window import BrowserWindow
from notte_core.credentials.base import BaseVault
from notte_core.llms.engine import LlmModel
from notte_sdk.types import DEFAULT_MAX_NB_STEPS

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
        vault: BaseVault | None = None,
        notifier: BaseNotifier | None = None,
    ):
        self.config: FalcoAgentConfig = (
            FalcoAgentConfig()
            .use_vision(use_vision)
            .model(reasoning_model, deep=True)
            .map_env(lambda env: (env.agent_mode().steps(max_steps).headless(headless).web_security(web_security)))
        )
        self.vault: BaseVault | None = vault
        self.notifier: BaseNotifier | None = notifier

    def create_agent(
        self,
        step_callback: Callable[[str, StepAgentOutput], None] | None = None,
        window: BrowserWindow | None = None,
    ) -> BaseAgent:
        agent = FalcoAgent(
            config=self.config,
            vault=self.vault,
            window=window,
            step_callback=step_callback,
        )
        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return agent

    async def async_run(self, task: str, url: str | None = None) -> AgentResponse:
        agent = self.create_agent()
        return await agent.run(task, url=url)

    def run(self, task: str, url: str | None = None) -> AgentResponse:
        agent = self.create_agent()
        return asyncio.run(agent.run(task, url=url))
