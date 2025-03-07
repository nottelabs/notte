import asyncio

from notte.agents.falco.agent import FalcoAgent, FalcoAgentConfig
from notte.common.agent.types import AgentResponse
from notte.common.credential_vault.base import BaseVault
from notte.llms.engine import LlmModel
from notte.sdk.types import DEFAULT_MAX_NB_STEPS


class Agent:
    def __init__(
        self,
        headless: bool = False,
        reasoning_model: str = LlmModel.default(),  # type: ignore[reportCallInDefaultInitializer]
        max_steps: int = DEFAULT_MAX_NB_STEPS,
        use_vision: bool = False,
        disable_web_security: bool = True,
        vault: BaseVault | None = None,
    ):
        self.config: FalcoAgentConfig = (
            FalcoAgentConfig()
            .use_vision(use_vision)
            .model(reasoning_model, deep=True)
            .map_env(lambda env: env.user_mode().steps(max_steps).headless(headless))
        )
        if disable_web_security:
            self.config = self.config.map_env(lambda env: env.disable_web_security())
        self.vault: BaseVault | None = vault

    def run(self, task: str) -> AgentResponse:
        agent = FalcoAgent(config=self.config, vault=self.vault)
        return asyncio.run(agent.run(task))
