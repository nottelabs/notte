from collections.abc import Callable

from loguru import logger
from typing_extensions import override

from notte.agents.gufo.parser import GufoParser
from notte.agents.gufo.perception import GufoPerception
from notte.agents.gufo.prompt import GufoPrompt
from notte.browser.observation import Observation
from notte.browser.pool.base import BaseBrowserPool
from notte.common.agent.base import BaseAgent
from notte.common.agent.config import AgentConfig
from notte.common.agent.parser import NotteStepAgentOutput
from notte.common.agent.types import AgentResponse
from notte.common.credential_vault.base import BaseVault
from notte.common.tools.conversation import Conversation
from notte.common.tracer import LlmUsageDictTracer
from notte.controller.actions import CompletionAction
from notte.env import NotteEnv, NotteEnvConfig
from notte.llms.engine import LLMEngine


class GufoAgentConfig(AgentConfig):
    @classmethod
    @override
    def default_env(cls) -> NotteEnvConfig:
        return NotteEnvConfig().use_llm()


class GufoAgent(BaseAgent):
    """
    A base agent implementation that coordinates between an LLM and the Notte environment.

    This class demonstrates how to build an agent that can:
    1. Maintain a conversation with an LLM
    2. Execute actions in the Notte environment
    3. Parse and format responses between the LLM and Notte

    To customize this agent:
    1. Implement your own Parser class to format observations and actions
    2. Modify the conversation flow in the run() method
    3. Adjust the think() method to handle LLM interactions
    4. Customize the ask_notte() method for your specific needs

    Args:
        task (str): The task description for the agent
        model (str): The LLM model identifier
        max_steps (int): Maximum number of steps before terminating
        headless (bool): Whether to run browser in headless mode
        parser (Parser | None): Custom parser for formatting interactions
    """

    def __init__(
        self,
        config: AgentConfig,
        vault: BaseVault | None = None,
        pool: BaseBrowserPool | None = None,
        step_callback: Callable[[str, NotteStepAgentOutput], None] | None = None,
    ) -> None:
        self.step_callback: Callable[[str, NotteStepAgentOutput], None] | None = step_callback
        self.tracer: LlmUsageDictTracer = LlmUsageDictTracer()
        self.config: AgentConfig = config
        self.vault: BaseVault | None = vault
        self.llm: LLMEngine = LLMEngine(
            model=config.reasoning_model,
            tracer=self.tracer,
            structured_output_retries=config.env.structured_output_retries,
            verbose=self.config.verbose,
        )
        # Users should implement their own parser to customize how observations
        # and actions are formatted for their specific LLM and use case
        self.env: NotteEnv = NotteEnv(
            config=config.env,
            pool=pool,
        )
        self.parser: GufoParser = GufoParser()
        self.prompt: GufoPrompt = GufoPrompt(self.parser)
        self.perception: GufoPerception = GufoPerception()
        self.conv: Conversation = Conversation()

    async def reset(self):
        await self.env.reset()
        self.conv.reset()

    def output(self, answer: str, success: bool) -> AgentResponse:
        return AgentResponse(
            answer=answer,
            success=success,
            env_trajectory=self.env.trajectory,
            agent_trajectory=[],
            llm_usage=self.tracer.usage,
        )

    async def step(self, task: str) -> CompletionAction | None:
        # Processes the conversation history through the LLM to decide the next action.
        # logger.info(f"🤖 LLM prompt:\n{self.conv.messages()}")
        response: str = self.llm.single_completion(self.conv.messages())
        self.conv.add_assistant_message(content=response)
        logger.info(f"🤖 LLM response:\n{response}")
        # Ask Notte to perform the selected action
        parsed_response = self.parser.parse(response)

        if parsed_response is None or parsed_response.action is None:
            self.conv.add_user_message(content=self.prompt.env_rules())
            return None

        if self.step_callback is not None:
            self.step_callback(task, parsed_response)

        if parsed_response.completion is not None:
            return parsed_response.completion
        action = parsed_response.action
        # Replace credentials if needed using the vault
        if self.vault is not None and self.vault.contains_credentials(action):
            action = self.vault.replace_credentials(action, self.env.snapshot)
        # Execute the action
        obs: Observation = await self.env.act(action)
        text_obs = self.perception.perceive(obs)
        self.conv.add_user_message(
            content=f"""
{text_obs}
{self.prompt.select_action_rules()}
{self.prompt.completion_rules()}
""",
            image=obs.screenshot if self.config.include_screenshot else None,
        )
        logger.info(f"🌌 Action successfully executed:\n{text_obs}")
        return None

    @override
    async def run(self, task: str, url: str | None = None) -> AgentResponse:
        """
        Main execution loop that coordinates between the LLM and Notte environment.

        This method shows a basic conversation flow. Consider customizing:
        1. The initial system prompt
        2. How observations are added to the conversation
        3. When and how to determine task completion
        4. Error handling and recovery strategies
        """
        logger.info(f"🚀 starting agent with task: {task} and url: {url}")
        system_msg = self.prompt.system(task, url)
        if self.vault is not None:
            system_msg += "\n" + self.vault.instructions()
        self.conv.add_system_message(content=system_msg)
        self.conv.add_user_message(self.prompt.env_rules())
        async with self.env:
            for i in range(self.config.env.max_steps):
                logger.info(f"> step {i}: looping in")
                output = await self.step(task=task)
                if output is not None:
                    status = "😎 task completed sucessfully" if output.success else "👿 task failed"
                    logger.info(f"{status} with answer: {output.answer}")
                    return self.output(output.answer, output.success)
            # If the task is not done, raise an error
            error_msg = f"Failed to solve task in {self.config.env.max_steps} steps"
            logger.info(f"🚨 {error_msg}")
            return self.output(error_msg, False)
