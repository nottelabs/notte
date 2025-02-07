from litellm import OpenAIMessageContent, override
from loguru import logger

from examples.simple.perception import SimplePerception
from examples.simple.prompt import SimplePrompt
from examples.simple.types import StepAgentOutput
from notte.browser.observation import Observation
from notte.common.agent import AgentOutput, BaseAgent
from notte.common.conversation import Conversation
from notte.common.safe_executor import SafeActionExecutor
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
        short_history: bool = True,
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
        )
        self.validator: TaskOutputValidator = TaskOutputValidator(llm=self.llm)
        self.max_actions_per_step: int = max_actions_per_step
        self.prompt: SimplePrompt = SimplePrompt(max_actions_per_step)
        self.conv: Conversation = Conversation(max_tokens=max_history_tokens, convert_tools_to_assistant=True)
        self.perception: SimplePerception = SimplePerception()
        self.short_history: bool = short_history
        self.trajectory: TrajectoryHistory = TrajectoryHistory(max_error_length=max_error_length)
        self.step_executor: SafeActionExecutor[BaseAction, Observation] = SafeActionExecutor(
            func=self.env.raw_step,
            raise_on_failure=raise_on_failure,
            max_consecutive_failures=max_consecutive_failures,
        )

    @override
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        """Execute the task with maximum number of steps"""
        system_msg, task_msg = self.prompt.system(), self.prompt.task(task)
        self.conv.add_system_message(content=system_msg)
        _ = self.conv.add_user_message(content=task_msg)

        max_steps = self.env.config.max_steps
        last_obs: OpenAIMessageContent | None = None
        # Loop through the steps
        async with self.env:
            for step in range(max_steps):
                logger.info(f"> step {step}: looping in")
                if self.short_history:
                    # Clear the conversation and add the system message
                    self.conv.clear()
                    self.conv.add_system_message(content=system_msg)
                    _ = self.conv.add_user_message(content=task_msg)
                    # Add the short trajectory execution history
                    traj_msg = self.trajectory.perceive()
                    logger.info(f"🔍 Trajectory history:\n{traj_msg}")
                    _ = self.conv.add_user_message(content=traj_msg)
                    # Add the last observation
                    if last_obs is not None:
                        _ = self.conv.add_user_message(content=last_obs)

                # Let the LLM Agent think about the next action
                # logger.info(
                #     "\n\n".join([f"# Message {i}: {m.role}\n{m.content}" for i, m in enumerate(self.conv.messages())])
                # )
                response: StepAgentOutput = self.llm.structured_completion(
                    self.conv.messages(), response_format=StepAgentOutput
                )
                logger.info(f"🔍 LLM response:\n{response}")

                self.conv.add_tool_message(response, tool_id="step")
                # check for completion
                if response.output is not None:
                    if not response.output.success:
                        logger.error(f"🚨 Task failed with reason: {response.output.answer}")
                        raise ValueError(f"Task failed with reason: {response.output.answer}")
                    # Sucessful execution and LLM output is not None
                    # Need to validate the output
                    logger.info(f"🔥 Validating agent output:\n{response.output.model_dump_json()}")
                    if not self.validator.validate(task, response.output, self.env.trajectory[-1]):
                        # TODO handle that differently
                        raise ValueError(f"Validation failed for task {task} with output {response.output}")
                    logger.info("✅ Task completed successfully")
                    return AgentOutput(
                        answer=response.output.answer,
                        success=response.output.success,
                        trajectory=self.env.trajectory,
                        messages=self.conv.messages(),
                    )
                # Execute the actions
                for action in response.get_actions()[: self.max_actions_per_step]:
                    result = await self.step_executor.execute(action)
                    self.trajectory.add_step(response, result)
                    step_msg = self.trajectory.perceive_step_result(result, include_ids=True)
                    if not result.success:
                        logger.error(f"🚨 {step_msg}")
                        # stop the loop
                        break
                    # Successfully executed the action
                    logger.info(f"🚀 {step_msg}")
                    last_obs = self.conv.add_user_message(
                        content=self.perception.perceive(result.get()),
                        image=result.get().screenshot if self.include_screenshot else None,
                    )

        error_msg = f"Failed to solve task in {max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        return AgentOutput(
            answer=error_msg,
            success=False,
            trajectory=self.env.trajectory,
            messages=self.conv.messages(),
        )
