import asyncio

from notte.agents.falco.agent import FalcoAgent, FalcoAgentConfig
from notte.common.agent.types import AgentResponse
from notte.common.credential_vault.base import BaseVault
from notte.common.notifier.base import BaseNotifier, NotifierAgent
from notte.llms.engine import LlmModel
from notte.sdk.types import DEFAULT_MAX_NB_STEPS


class Agent:
    def __init__(
        self,
        headless: bool = False,
        reasoning_model: str = LlmModel.default(),  # type: ignore[reportCallInDefaultInitializer]
        max_steps: int = DEFAULT_MAX_NB_STEPS,
        use_vision: bool = False,
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

    def run(self, task: str) -> AgentResponse:
        agent = FalcoAgent(config=self.config, vault=self.vault)
        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return asyncio.run(agent.run(task))
