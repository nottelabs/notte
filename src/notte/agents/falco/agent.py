import time
import traceback
import typing
from collections.abc import Callable
from enum import StrEnum

from litellm import AllMessageValues, override
from loguru import logger

import notte
from notte.browser.observation import Observation
from notte.browser.pool.base import BaseBrowserPool
from notte.browser.window import BrowserWindow
from notte.common.agent.base import BaseAgent
from notte.common.agent.config import AgentConfig, RaiseCondition
from notte.common.agent.types import AgentResponse
from notte.common.credential_vault.base import BaseVault
from notte.common.tools.conversation import Conversation
from notte.common.tools.safe_executor import ExecutionStatus, SafeActionExecutor
from notte.common.tools.trajectory_history import TrajectoryHistory
from notte.common.tools.validator import CompletionValidator
from notte.common.tracer import LlmUsageDictTracer
from notte.controller.actions import BaseAction, CompletionAction, FallbackObserveAction
from notte.env import NotteEnv, NotteEnvConfig
from notte.llms.engine import LLMEngine
from notte.llms.service import LLMService
from notte.pipe.resolution.nudge import NudgeAnalysisResult, NudgePipe

from .perception import FalcoPerception
from .prompt import FalcoPrompt
from .types import StepAgentOutput

# TODO: list
# handle tooling calling methods for different providers (if not supported by litellm)
# Handle control flags
# Done callback
# Setup telemetry
# Setup memory
# Handle custom functions, e.g. `Upload file to element`ç
# Remove base 64 images from current state
# TODO: add fault tolerance LLM parsing
# TODO: only display modal actions when modal is open (same as before)
# TODO: handle prevent default click JS events
# TODO: add some tree structure for menu elements (like we had in notte before. Ex. Menu in Arxiv)


class HistoryType(StrEnum):
    FULL_CONVERSATION = "full_conversation"
    SHORT_OBSERVATIONS = "short_observations"
    SHORT_OBSERVATIONS_WITH_RAW_DATA = "short_observations_with_raw_data"
    SHORT_OBSERVATIONS_WITH_SHORT_DATA = "short_observations_with_short_data"
    COMPRESSED = "compressed"


class FalcoAgentConfig(AgentConfig):
    max_actions_per_step: int = 1
    history_type: HistoryType = HistoryType.SHORT_OBSERVATIONS_WITH_SHORT_DATA
    enable_nudges: bool = True
    nudge_max_steps_to_analyze: int = 3
    nudge_failure_threshold: int = 3
    nudge_max_tokens: int = 1000

    @classmethod
    @override
    def default_env(cls) -> NotteEnvConfig:
        return NotteEnvConfig().disable_perception()


class FalcoAgent(BaseAgent):
    def __init__(
        self,
        config: FalcoAgentConfig,
        pool: BaseBrowserPool | None = None,
        window: BrowserWindow | None = None,
        vault: BaseVault | None = None,
        step_callback: Callable[[str, StepAgentOutput], None] | None = None,
    ):
        self.config: FalcoAgentConfig = config
        self.vault: BaseVault | None = vault

        if config.include_screenshot and not config.env.window.screenshot:
            raise ValueError("Cannot `include_screenshot=True` if `screenshot` is not enabled in the browser config")
        self.tracer: LlmUsageDictTracer = LlmUsageDictTracer()
        self.llm: LLMEngine = LLMEngine(
            model=config.reasoning_model,
            tracer=self.tracer,
            structured_output_retries=config.env.structured_output_retries,
        )
        self.step_callback: Callable[[str, StepAgentOutput], None] | None = step_callback
        # Users should implement their own parser to customize how observations
        # and actions are formatted for their specific LLM and use case
        self.env: NotteEnv = NotteEnv(
            config=config.env,
            pool=pool,
            window=window,
        )
        self.perception: FalcoPerception = FalcoPerception()
        self.validator: CompletionValidator = CompletionValidator(llm=self.llm, perception=self.perception)
        self.prompt: FalcoPrompt = FalcoPrompt(max_actions_per_step=config.max_actions_per_step)
        self.conv: Conversation = Conversation(
            max_tokens=config.max_history_tokens,
            convert_tools_to_assistant=True,
            autosize=True,
            model=config.reasoning_model,
        )
        self.history_type: HistoryType = config.history_type
        self.trajectory: TrajectoryHistory = TrajectoryHistory(max_error_length=config.max_error_length)
        self.step_executor: SafeActionExecutor[BaseAction, Observation] = SafeActionExecutor(
            func=self.env.act,
            raise_on_failure=(self.config.raise_condition is RaiseCondition.IMMEDIATELY),
            max_consecutive_failures=config.max_consecutive_failures,
        )

        # Initialize the nudge pipe if enabled
        self.nudge_pipe: NudgePipe | None = None
        if config.enable_nudges:
            llmserve = LLMService(base_model=config.reasoning_model)
            self.nudge_pipe = NudgePipe(llmserve)

        # Track the last nudge result to avoid repeating the same nudges
        self.last_nudge_result: NudgeAnalysisResult | None = None

    async def reset(self) -> None:
        self.conv.reset()
        self.trajectory.reset()
        self.step_executor.reset()
        await self.env.reset()

    def output(self, answer: str, success: bool) -> AgentResponse:
        return AgentResponse(
            answer=answer,
            success=success,
            env_trajectory=self.env.trajectory,
            agent_trajectory=self.trajectory.steps,
            messages=self.conv.messages(),
            duration_in_s=time.time() - self.start_time,
            llm_usage=self.tracer.usage,
        )

    def get_messages(self, task: str) -> list[AllMessageValues]:
        self.conv.reset()
        system_msg, task_msg = self.prompt.system(), self.prompt.task(task)
        if self.vault is not None:
            system_msg += "\n" + self.vault.instructions()
        self.conv.add_system_message(content=system_msg)
        self.conv.add_user_message(content=task_msg)
        # just for logging
        traj_msg = self.trajectory.perceive()
        logger.info(f"🔍 Trajectory history:\n{traj_msg}")

        # Check if nudges are needed
        nudge_msg = ""
        if self.config.enable_nudges and self.nudge_pipe is not None and len(self.trajectory.steps) > 0:
            # Analyze the trajectory and get nudges if needed
            self.last_nudge_result = self.nudge_pipe.forward(
                self.trajectory,
                max_steps_to_analyze=self.config.nudge_max_steps_to_analyze,
                failure_threshold=self.config.nudge_failure_threshold,
                max_tokens=self.config.nudge_max_tokens,
            )

            # If nudges are needed, add them to the message
            if self.last_nudge_result.needs_nudge:
                nudge_msg = self.last_nudge_result.get_formatted_hints()
                logger.info(f"🚨 Adding nudges to agent prompt:\n{nudge_msg}")

        # add trajectory to the conversation
        match self.history_type:
            case HistoryType.COMPRESSED:
                self.conv.add_user_message(content=traj_msg)
                # Add nudges if needed
                if nudge_msg:
                    self.conv.add_user_message(content=nudge_msg)
            case _:
                if len(self.trajectory.steps) == 0:
                    self.conv.add_user_message(content=self.trajectory.start_rules())
                for step in self.trajectory.steps:
                    # TODO: choose if we want this to be an assistant message or a tool message
                    # self.conv.add_tool_message(step.agent_response, tool_id="step")
                    self.conv.add_assistant_message(step.agent_response.model_dump_json(exclude_none=True))
                    for result in step.results:
                        short_step_msg = self.trajectory.perceive_step_result(result, include_ids=True)
                        self.conv.add_user_message(content=short_step_msg)
                        if not result.success:
                            continue
                        # add observation data to the conversation
                        obs = result.get()
                        match (self.history_type, obs.has_data()):
                            case (HistoryType.FULL_CONVERSATION, _):
                                self.conv.add_user_message(
                                    content=self.perception.perceive(obs),
                                    image=(obs.screenshot if self.config.include_screenshot else None),
                                )
                            case (HistoryType.SHORT_OBSERVATIONS_WITH_RAW_DATA, True):
                                # add data if data was scraped
                                self.conv.add_user_message(content=self.perception.perceive_data(obs, raw=True))

                            case (HistoryType.SHORT_OBSERVATIONS_WITH_SHORT_DATA, True):
                                self.conv.add_user_message(content=self.perception.perceive_data(obs, raw=False))
                            case _:
                                pass

                # Add nudges if needed
                if nudge_msg:
                    self.conv.add_user_message(content=nudge_msg)

        last_valid_obs = self.trajectory.last_obs()
        if last_valid_obs is not None and self.history_type is not HistoryType.FULL_CONVERSATION:
            self.conv.add_user_message(
                content=self.perception.perceive(last_valid_obs),
                image=(last_valid_obs.screenshot if self.config.include_screenshot else None),
            )

        if len(self.trajectory.steps) > 0:
            self.conv.add_user_message(self.prompt.action_message())

        return self.conv.messages()

    async def step(self, task: str) -> CompletionAction | None:
        """Execute a single step of the agent"""
        messages = self.get_messages(task)
        response: StepAgentOutput = self.llm.structured_completion(messages, response_format=StepAgentOutput)
        if self.step_callback is not None:
            self.step_callback(task, response)
        logger.info(f"🔍 LLM response:\n{response}")
        self.trajectory.add_output(response)
        # check for completion
        if response.output is not None:
            return response.output
        # Execute the actions
        for action in response.get_actions(self.config.max_actions_per_step):
            # Replace credentials if needed using the vault
            if self.vault is not None and self.vault.contains_credentials(action):
                action = self.vault.replace_credentials(action, self.env.snapshot)

            result = await self.step_executor.execute(action)

            self.trajectory.add_step(result)
            step_msg = self.trajectory.perceive_step_result(result, include_ids=True)
            if not result.success:
                logger.error(f"🚨 {step_msg}")

                # observe again
                obs = await self.env.observe()

                # cast is necessary because we cant have covariance
                # in ExecutionStatus
                ex_status = ExecutionStatus(
                    input=typing.cast(BaseAction, FallbackObserveAction()),
                    output=obs,
                    success=True,
                    message="Observed",
                )
                self.trajectory.add_output(response)
                self.trajectory.add_step(ex_status)

                # stop the loop
                break
            # Successfully executed the action
            logger.info(f"🚀 {step_msg}")
        return None

    @override
    async def run(self, task: str, url: str | None = None) -> AgentResponse:
        self.start_time: float = time.time()
        try:
            return await self._run(task, url=url)

        except Exception as e:
            if self.config.raise_condition is RaiseCondition.NEVER:
                return self.output(f"Failed due to {e}: {traceback.format_exc()}", False)
            raise e

    async def _run(self, task: str, url: str | None = None) -> AgentResponse:
        """Execute the task with maximum number of steps"""
        # change this to DEV if you want more explicit error messages
        # when you are developing your own agent
        notte.set_error_mode("agent")
        if url is not None:
            task = f"Start on '{url}' and {task}"

        # Loop through the steps
        async with self.env:
            for step in range(self.env.config.max_steps):
                logger.info(f"> step {step}: looping in")
                output: CompletionAction | None = await self.step(task)

                if output is None:
                    continue
                # validate the output
                if not output.success:
                    logger.error(f"🚨 Agent terminated early with failure: {output.answer}")
                    return self.output(output.answer, False)
                # Sucessful execution and LLM output is not None
                # Need to validate the output
                logger.info(f"🔥 Validating agent output:\n{output.model_dump_json()}")
                val = self.validator.validate(task, output, self.env.trajectory[-1])
                if val.is_valid:
                    # Successfully validated the output
                    logger.info("✅ Task completed successfully")
                    return self.output(output.answer, output.success)
                else:
                    # TODO handle that differently
                    failed_val_msg = f"Final validation failed: {val.reason}. Continuing..."
                    logger.error(failed_val_msg)
                    # add the validation result to the trajectory and continue
                    self.trajectory.add_step(
                        ExecutionStatus(
                            input=output,
                            output=None,
                            success=False,
                            message=failed_val_msg,
                        )
                    )

        error_msg = f"Failed to solve task in {self.env.config.max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        notte.set_error_mode("developer")
        return self.output(error_msg, False)
