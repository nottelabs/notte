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
from notte.common.safe_executor import ExecutionStatus, SafeActionExecutor
from notte.common.trajectory_history import TrajectoryHistory
from notte.common.validator import TaskOutputValidator
from notte.controller.actions import BaseAction
from notte.env import NotteEnv, NotteEnvConfig
from notte.llms.engine import LLMEngine

config = NotteEnvConfig.simple()

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
    ONLY_DECISIONS = "only_decisions"
    COMPRESSED = "compressed"


class SimpleAgent(BaseAgent):

    def __init__(
        self,
        model: str,
        headless: bool,
        include_screenshot: bool = False,
        max_history_tokens: int = 64000,
        max_error_length: int = 500,
        raise_on_failure: bool = False,
        max_consecutive_failures: int = 3,
        # TODO: enable multi-action later when we have a better prompt
        max_actions_per_step: int = 1,
        history_type: HistoryType = HistoryType.ONLY_DECISIONS,
        pool: BrowserPool | None = None,
    ):
        if include_screenshot and not config.browser.screenshot:
            raise ValueError("Cannot `include_screenshot=True` if `screenshot` is not enabled in the browser config")
        self.model: str = model
        self.include_screenshot: bool = include_screenshot
        self.llm: LLMEngine = LLMEngine(model=model)
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
            raise_on_failure=raise_on_failure,
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
            trajectory=self.env.trajectory,
            messages=self.conv.messages(),
        )

    def get_messages(self, task: str) -> list[AllMessageValues]:
        self.conv.reset()
        system_msg, task_msg = self.prompt.system(), self.prompt.task(task)
        self.conv.add_system_message(content=system_msg)
        self.conv.add_user_message(content=task_msg)
        match self.history_type:
            case HistoryType.COMPRESSED:
                traj_msg = self.trajectory.perceive()
                logger.info(f"🔍 Trajectory history:\n{traj_msg}")
                self.conv.add_user_message(content=traj_msg)
            case _:
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
                        if self.history_type is HistoryType.FULL_CONVERSATION:
                            self.conv.add_user_message(
                                content=self.perception.perceive(obs),
                                image=obs.screenshot if self.include_screenshot else None,
                            )
                        elif obs.has_data():
                            # add data if data was scraped
                            self.conv.add_user_message(content=self.perception.perceive_data(obs))

        last_valid_obs = self.trajectory.last_obs()
        if last_valid_obs is not None and self.history_type is not HistoryType.FULL_CONVERSATION:
            self.conv.add_user_message(
                content=self.perception.perceive(last_valid_obs),
                image=last_valid_obs.screenshot if self.include_screenshot else None,
            )
        return self.conv.messages()

    @override
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        """Execute the task with maximum number of steps"""
        # change this to DEV if you want more explicit error messages
        # when you are developing your own agent
        notte.set_error_mode("agent")
        if url is not None:
            task = f"Start on '{url}' and {task}"

        max_steps = self.env.config.max_steps
        # Loop through the steps
        async with self.env:
            self.conv.add_user_message(content=self.trajectory.start_rules())
            for step in range(max_steps):
                logger.info(f"> step {step}: looping in")
                messages = self.get_messages(task)
                response: StepAgentOutput = self.llm.structured_completion(messages, response_format=StepAgentOutput)
                logger.info(f"🔍 LLM response:\n{response}")
                self.trajectory.add_output(response)
                # check for completion
                if response.output is not None:
                    if not response.output.success:
                        logger.error(f"🚨 Task failed with reason: {response.output.answer}")
                        return self.output(response.output.answer, False)
                    # Sucessful execution and LLM output is not None
                    # Need to validate the output
                    logger.info(f"🔥 Validating agent output:\n{response.output.model_dump_json()}")
                    val = self.validator.validate(task, response.output, self.env.trajectory[-1])
                    if not val.is_valid:
                        # TODO handle that differently
                        failed_val_msg = f"final validation failed: {val.reason}"
                        logger.error(failed_val_msg)
                        # add the validation result to the trajectory and continue

                        self.trajectory.add_step(
                            ExecutionStatus(
                                input=response.get_actions()[-1],
                                output=None,
                                success=False,
                                message=failed_val_msg,
                            )
                        )
                        continue
                    # Successfully validated the output
                    logger.info("✅ Task completed successfully")
                    return self.output(response.output.answer, response.output.success)
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

        error_msg = f"Failed to solve task in {max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        notte.set_error_mode("developer")
        return self.output(error_msg, False)
