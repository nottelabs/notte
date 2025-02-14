import time
from enum import StrEnum

from litellm import AllMessageValues, override
from loguru import logger

import notte
from examples.simple.perception import SimplePerception
from examples.simple.prompt import SimplePrompt
from examples.simple.types import StepAgentOutput
from notte.browser.observation import Observation
from notte.browser.pool import BrowserPool
from notte.common.agent import AgentOutput, BaseAgent
from notte.common.conversation import Conversation
from notte.common.parser import TaskOutput
from notte.common.safe_executor import ExecutionStatus, SafeActionExecutor
from notte.common.tracer import LlmUsageDictTracer
from notte.common.trajectory_history import TrajectoryHistory
from notte.common.validator import TaskOutputValidator
from notte.controller.actions import BaseAction, CompletionAction
from notte.env import NotteEnv, NotteEnvConfig
from notte.llms.engine import LLMEngine

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


class RaiseCondition(StrEnum):
    """How to raise an error when the agent fails to complete a step.

    Either immediately upon failure, after retry, or never.
    """

    IMMEDIATELY = "immediately"
    RETRY = "retry"
    NEVER = "never"


class SimpleAgent(BaseAgent):

    def __init__(
        self,
        model: str,
        headless: bool,
        include_screenshot: bool = False,
        max_history_tokens: int = 64000,
        max_error_length: int = 500,
        raise_condition: RaiseCondition = RaiseCondition.RETRY,
        max_consecutive_failures: int = 3,
        # TODO: enable multi-action later when we have a better prompt
        max_actions_per_step: int = 1,
        history_type: HistoryType = HistoryType.SHORT_OBSERVATIONS_WITH_SHORT_DATA,
        pool: BrowserPool | None = None,
        disable_web_security: bool = False,
    ):
        config = NotteEnvConfig.simple()
        config.browser.disable_web_security = disable_web_security

        if include_screenshot and not config.browser.screenshot:
            raise ValueError("Cannot `include_screenshot=True` if `screenshot` is not enabled in the browser config")
        self.raise_condition: RaiseCondition = raise_condition
        self.model: str = model
        self.include_screenshot: bool = include_screenshot

        self.tracer: LlmUsageDictTracer = LlmUsageDictTracer()
        self.llm: LLMEngine = LLMEngine(model=model, tracer=self.tracer)

        # Users should implement their own parser to customize how observations
        # and actions are formatted for their specific LLM and use case
        self.env: NotteEnv = NotteEnv(
            headless=headless,
            config=config,
            pool=pool,
        )
        self.validator: TaskOutputValidator = TaskOutputValidator(llm=self.llm)
        self.max_actions_per_step: int = max_actions_per_step
        self.prompt: SimplePrompt = SimplePrompt(max_actions_per_step)
        self.conv: Conversation = Conversation(max_tokens=max_history_tokens, convert_tools_to_assistant=True)
        self.perception: SimplePerception = SimplePerception()
        self.history_type: HistoryType = history_type
        self.trajectory: TrajectoryHistory = TrajectoryHistory(max_error_length=max_error_length)
        self.step_executor: SafeActionExecutor[BaseAction, Observation] = SafeActionExecutor(
            func=self.env.raw_step,
            raise_on_failure=(raise_condition is RaiseCondition.IMMEDIATELY),
            max_consecutive_failures=max_consecutive_failures,
        )

    async def reset(self) -> None:
        self.conv.reset()
        self.trajectory.reset()
        self.step_executor.reset()
        await self.env.reset()

    def output(self, answer: str, success: bool) -> AgentOutput:
        return AgentOutput(
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
        self.conv.add_system_message(content=system_msg)
        self.conv.add_user_message(content=task_msg)
        # just for logging
        traj_msg = self.trajectory.perceive()
        logger.info(f"🔍 Trajectory history:\n{traj_msg}")
        # add trajectory to the conversation
        match self.history_type:
            case HistoryType.COMPRESSED:
                self.conv.add_user_message(content=traj_msg)
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
                                    image=obs.screenshot if self.include_screenshot else None,
                                )
                            case (HistoryType.SHORT_OBSERVATIONS_WITH_RAW_DATA, True):
                                # add data if data was scraped
                                self.conv.add_user_message(content=self.perception.perceive_data(obs, raw=True))
                            case (HistoryType.SHORT_OBSERVATIONS_WITH_SHORT_DATA, True):
                                self.conv.add_user_message(content=self.perception.perceive_data(obs, raw=False))
                            case _:
                                pass

        last_valid_obs = self.trajectory.last_obs()
        if last_valid_obs is not None and self.history_type is not HistoryType.FULL_CONVERSATION:
            self.conv.add_user_message(
                content=self.perception.perceive(last_valid_obs),
                image=last_valid_obs.screenshot if self.include_screenshot else None,
            )
        return self.conv.messages()

    async def step(self, task: str) -> TaskOutput | None:
        """Execute a single step of the agent"""
        messages = self.get_messages(task)
        logger.info(f"🔍 LLM messages:\n{messages}")
        response: StepAgentOutput = self.llm.structured_completion(messages, response_format=StepAgentOutput)
        logger.info(f"🔍 LLM response:\n{response}")
        self.trajectory.add_output(response)
        # check for completion
        if response.output is not None:
            return response.output
        # Execute the actions
        for action in response.get_actions(self.max_actions_per_step):
            result = await self.step_executor.execute(action)
            self.trajectory.add_step(result)
            step_msg = self.trajectory.perceive_step_result(result, include_ids=True)
            if not result.success:
                logger.error(f"🚨 {step_msg}")
                # stop the loop
                break
            # Successfully executed the action
            logger.info(f"🚀 {step_msg}")
        return None

    @override
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        self.start_time: float = time.time()
        try:
            return await self._run(task, url=url)

        except Exception as e:
            if self.raise_condition is RaiseCondition.NEVER:
                return self.output(f"Failed due to {e}", False)
            raise

    async def _run(self, task: str, url: str | None = None) -> AgentOutput:
        """Execute the task with maximum number of steps"""
        # change this to DEV if you want more explicit error messages
        # when you are developing your own agent
        notte.set_error_mode("agent")
        if url is not None:
            task = f"Start on '{url}' and {task}"

        max_steps = self.env.config.max_steps
        # Loop through the steps
        async with self.env:
            for step in range(max_steps):
                logger.info(f"> step {step}: looping in")
                output: TaskOutput | None = await self.step(task)

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
                            input=CompletionAction(
                                success=output.success,
                                answer=output.answer,
                            ),
                            output=None,
                            success=False,
                            message=failed_val_msg,
                        )
                    )

        error_msg = f"Failed to solve task in {max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        notte.set_error_mode("developer")
        return self.output(error_msg, False)
