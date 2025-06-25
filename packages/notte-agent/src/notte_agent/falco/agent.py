import datetime as dt
import json
import traceback
import typing
from collections.abc import Callable
from enum import StrEnum

import notte_core
from litellm import AllMessageValues, override
from loguru import logger
from notte_browser.session import NotteSession
from notte_browser.vault import VaultSecretsScreenshotMask
from notte_browser.window import BrowserWindow
from notte_core.actions import (
    BaseAction,
    CaptchaSolveAction,
    CompletionAction,
    FormFillAction,
)
from notte_core.common.config import NotteConfig, RaiseCondition
from notte_core.common.tracer import LlmUsageDictTracer
from notte_core.credentials.base import BaseVault, LocatorAttributes
from notte_core.llms.engine import LLMEngine
from notte_core.profiling import profiler
from notte_sdk.types import AgentCreateRequest, AgentCreateRequestDict, AgentRunRequest, AgentRunRequestDict
from pydantic import field_validator

from notte_agent.common.base import BaseAgent
from notte_agent.common.conversation import Conversation
from notte_agent.common.safe_executor import SafeActionExecutor
from notte_agent.common.trajectory_history import AgentTrajectoryHistory
from notte_agent.common.types import AgentResponse, AgentStepResponse
from notte_agent.common.validator import CompletionValidator
from notte_agent.falco.perception import FalcoPerception
from notte_agent.falco.prompt import FalcoPrompt

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


class FalcoConfig(NotteConfig):
    enable_perception: bool = False
    auto_scrape: bool = False
    history_type: HistoryType = HistoryType.SHORT_OBSERVATIONS_WITH_SHORT_DATA

    @field_validator("enable_perception")
    def check_perception(cls, value: bool) -> bool:
        if value:
            logger.warning("Perception should be disabled for falco. Don't set this argument to `True`.")
        return False

    @field_validator("auto_scrape")
    def check_auto_scrape(cls, value: bool) -> bool:
        if value:
            logger.warning("Auto scrape is not allowed for falco. Don't set this argument to another value.")
        return False


class FalcoAgent(BaseAgent):
    def __init__(
        self,
        window: BrowserWindow,
        vault: BaseVault | None = None,
        step_callback: Callable[[AgentStepResponse], None] | None = None,
        **data: typing.Unpack[AgentCreateRequestDict],
    ):
        _ = AgentCreateRequest.model_validate(data)
        self.config: FalcoConfig = FalcoConfig.from_toml(**data)
        session = NotteSession(window=window, enable_perception=False)
        super().__init__(session=session)
        self.vault: BaseVault | None = vault

        self.tracer: LlmUsageDictTracer = LlmUsageDictTracer()
        self.llm: LLMEngine = LLMEngine(model=self.config.reasoning_model, tracer=self.tracer)

        self.step_callback: Callable[[AgentStepResponse], None] | None = step_callback
        # Users should implement their own parser to customize how observations
        # and actions are formatted for their specific LLM and use case

        if self.vault is not None:
            # hide vault leaked credentials within llm inputs
            self.llm.structured_completion = self.vault.patch_structured_completion(0, self.vault.get_replacement_map)(  # pyright: ignore [reportAttributeAccessIssue]
                self.llm.structured_completion
            )

        self.perception: FalcoPerception = FalcoPerception()
        self._validator: CompletionValidator | None = None
        self.prompt: FalcoPrompt = FalcoPrompt(max_actions_per_step=self.config.max_actions_per_step)
        self.conv: Conversation = Conversation(
            convert_tools_to_assistant=True,
            autosize=True,
            model=self.config.reasoning_model,
        )
        self.trajectory: AgentTrajectoryHistory = AgentTrajectoryHistory(max_steps=self.config.max_steps)
        self.created_at: dt.datetime = dt.datetime.now()
        self.step_executor: SafeActionExecutor = SafeActionExecutor(session=self.session)

    @property
    def validator(self) -> CompletionValidator:
        if self._validator is not None:
            return self._validator

        self._validator = CompletionValidator(
            llm=self.llm, perception=self.perception, use_vision=self.config.use_vision
        )
        return self._validator

    async def action_with_credentials(self, action: BaseAction) -> BaseAction:
        if self.vault is not None and self.vault.contains_credentials(action):
            locator = await self.session.locate(action)

            attrs = LocatorAttributes(type=None, autocomplete=None, outerHTML=None)
            if locator is not None:
                # compute locator attributes
                attr_type = await locator.get_attribute("type")
                autocomplete = await locator.get_attribute("autocomplete")
                outer_html = await locator.evaluate("el => el.outerHTML")
                attrs = LocatorAttributes(type=attr_type, autocomplete=autocomplete, outerHTML=outer_html)

            if locator is not None or isinstance(action, FormFillAction):
                action = self.vault.replace_credentials(
                    action,
                    attrs,
                    self.session.snapshot,
                )
        return action

    async def reset(self) -> None:
        self.conv.reset()
        self.trajectory.reset()
        self.step_executor.reset()
        await self.session.areset()
        self.created_at = dt.datetime.now()

    def output(self, answer: str, success: bool) -> AgentResponse:
        return AgentResponse(
            created_at=self.created_at,
            closed_at=dt.datetime.now(),
            answer=answer,
            success=success,
            trajectory=self.trajectory.steps,
            llm_messages=self.conv.messages(),
            llm_usage=self.tracer.usage,
        )

    async def get_messages(self, task: str) -> list[AllMessageValues]:
        self.conv.reset()
        system_msg, task_msg = self.prompt.system(), self.prompt.task(task)
        if self.vault is not None:
            system_msg += "\n" + self.vault.instructions()
        self.conv.add_system_message(content=system_msg)
        self.conv.add_user_message(content=task_msg)
        # just for logging
        traj_msg = self.trajectory.perceive()
        if self.config.verbose:
            logger.trace(f"🔍 Trajectory history:\n{traj_msg}")
        # add trajectory to the conversation
        match self.config.history_type:
            case HistoryType.COMPRESSED:
                self.conv.add_user_message(content=traj_msg)
            case _:
                if len(self.trajectory.steps) == 0:
                    self.conv.add_user_message(content=self.trajectory.start_rules())
                for step in self.trajectory.steps:
                    # TODO: choose if we want this to be an assistant message or a tool message
                    # self.conv.add_tool_message(step.agent_response, tool_id="step")

                    # remove the previous ids as they might have changed
                    response_no_relevant = step.agent_response.model_dump(exclude_none=True)
                    response_no_relevant["state"]["relevant_interactions"] = []

                    self.conv.add_assistant_message(json.dumps(response_no_relevant))

                    for result in step.results:
                        short_step_msg = self.trajectory.perceive_step_result(result, include_ids=True)
                        self.conv.add_user_message(content=short_step_msg)
                        if not result.result.success:
                            continue
                        # add observation data to the conversation
                        obs = result.obs
                        match (self.config.history_type, obs.has_data()):
                            case (HistoryType.FULL_CONVERSATION, _):
                                self.conv.add_user_message(
                                    content=self.perception.perceive(obs),
                                    image=(obs.screenshot if self.config.use_vision else None),
                                )
                            case (HistoryType.SHORT_OBSERVATIONS_WITH_RAW_DATA, True):
                                # add data if data was scraped
                                self.conv.add_user_message(content=self.perception.perceive_data(obs, raw=True))

                            case (HistoryType.SHORT_OBSERVATIONS_WITH_SHORT_DATA, True):
                                self.conv.add_user_message(content=self.perception.perceive_data(obs, raw=False))
                            case _:
                                pass

        last_valid_obs = self.trajectory.last_obs()
        if last_valid_obs is not None and self.config.history_type is not HistoryType.FULL_CONVERSATION:
            self.conv.add_user_message(
                content=self.perception.perceive(last_valid_obs),
                image=(last_valid_obs.screenshot if self.config.use_vision else None),
            )

        if len(self.trajectory.steps) > 0:
            self.conv.add_user_message(self.prompt.action_message())

        return self.conv.messages()

    @profiler.profiled()
    async def step(self, task: str) -> CompletionAction | None:
        """Execute a single step of the agent"""
        messages = await self.get_messages(task)
        response: AgentStepResponse = await self.llm.structured_completion(
            messages, response_format=AgentStepResponse, use_strict_response_format=False
        )

        if self.step_callback is not None:
            self.step_callback(response)

        if self.config.verbose:
            logger.trace(f"🔍 LLM response:\n{response}")

        for text, data in response.log_state():
            logger.opt(colors=True).info(text, **data)

        self.trajectory.add_agent_response(response)
        # check for completion
        if response.output is not None:
            return response.output
        # Execute the actions
        for action in response.get_actions():
            if isinstance(action, CaptchaSolveAction) and not self.session.window.resource.options.solve_captchas:
                return CompletionAction(
                    success=False,
                    answer=f"Agent encountered {action.captcha_type} captcha but session doesnt solve captchas: create a session with solve_captchas=True",
                )

            action_with_credentials = await self.action_with_credentials(action)
            result = await self.step_executor.execute(action_with_credentials)
            self.trajectory.add_step(result)
            step_msg = self.trajectory.perceive_step_result(result, include_ids=True)
            logger.info(f"{step_msg}\n\n")
            if not result.result.success:
                # stop the loop if the action failed
                break

            # Successfully executed the action
        return None

    @profiler.profiled()
    @override
    async def run(self, **kwargs: typing.Unpack[AgentRunRequestDict]) -> AgentResponse:
        request = AgentRunRequest.model_validate(kwargs)
        logger.trace(f"Running task: {request.task}")
        self.created_at = dt.datetime.now()
        try:
            return await self._run(request)

        except Exception as e:
            if self.config.raise_condition is RaiseCondition.NEVER:
                return self.output(f"Failed due to {e}: {traceback.format_exc()}", False)
            raise e

    async def _run(self, request: AgentRunRequest) -> AgentResponse:
        """Execute the task with maximum number of steps"""
        # change this to DEV if you want more explicit error messages
        # when you are developing your own agent
        notte_core.set_error_mode("agent")
        if request.url is not None:
            request.task = f"Start on '{request.url}' and {request.task}"

        # hide vault leaked credentials within screenshots
        if self.vault is not None:
            self.session.window.screenshot_mask = VaultSecretsScreenshotMask(vault=self.vault)

        for step in range(self.config.max_steps):
            logger.info(f"💡 Step {step}")
            output: CompletionAction | None = await self.step(task=request.task)

            if output is None:
                continue
            # validate the output
            if not output.success:
                logger.error(f"🚨 Agent terminated early with failure: {output.answer}")
                return self.output(output.answer, False)
            # Sucessful execution and LLM output is not None
            # Need to validate the output
            logger.info(f"🔥 Validating agent output:\n{output.model_dump_json()}")
            val = await self.validator.validate(
                task=request.task,
                output=output,
                history=self.trajectory,
                response_format=request.response_format,
            )
            if val.is_valid:
                # Successfully validated the output
                logger.info("✅ Task completed successfully")
                return self.output(output.answer, output.success)
            else:
                # TODO handle that differently
                failed_val_msg = f"""Final validation failed: {val.reason}. Continuing...
                CRITICAL: If you think this validation is wrong: argue why the task if finished, or
                perform actions that would prove it is.
                """
                logger.error(failed_val_msg)
                # add the validation result to the trajectory and continue
                failed_step = await self.step_executor.fail(output, failed_val_msg)
                self.trajectory.add_step(failed_step)

        error_msg = f"Failed to solve task in {self.config.max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        notte_core.set_error_mode("developer")
        return self.output(error_msg, False)
