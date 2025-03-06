import asyncio

from notte.agents.falco.agent import (
    FalcoAgent as Agent,
)
from notte.agents.falco.agent import (
    FalcoAgentConfig as AgentConfig,
)
from notte.common.agent.types import AgentResponse
from notte.sdk.types import DEFAULT_MAX_NB_STEPS


class MarcelAgent:
    def __init__(
        self,
        headless: bool = True,
        reasoning_model: str = "gemini/gemini-2.0-flash",
        max_steps: int = DEFAULT_MAX_NB_STEPS,
        disable_web_security: bool = True,
    ):
        self.config: AgentConfig = AgentConfig(reasoning_model=reasoning_model).map_env(
            lambda env: env.user_mode().steps(max_steps).headless(headless)
        )
        if disable_web_security:
            self.config = self.config.map_env(lambda env: env.disable_web_security())

    def run(self, task: str) -> AgentResponse:
        agent = Agent(config=self.config)
        return asyncio.run(agent.run(task))
