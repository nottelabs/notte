import datetime as dt
import traceback
import typing

from litellm import AllMessageValues
from loguru import logger
from notte_browser.session import NotteSession
from notte_browser.vault import VaultSecretsScreenshotMask
from notte_core.actions import (
    BaseAction,
    CaptchaSolveAction,
    CompletionAction,
    FormFillAction,
    GotoAction,
)
from notte_core.agent_types import AgentCompletion
from notte_core.browser.observation import ExecutionResult, Observation, TrajectoryProgress
from notte_core.common.config import NotteConfig, RaiseCondition
from notte_core.common.telemetry import track_usage
from notte_core.common.tracer import LlmUsageDictTracer
from notte_core.credentials.base import BaseVault, LocatorAttributes
from notte_core.errors.base import ErrorConfig, NotteBaseError
from notte_core.llms.engine import LLMEngine
from notte_core.profiling import profiler
from notte_core.trajectory import Trajectory
from notte_sdk.types import AgentRunRequest, AgentRunRequestDict
from typing_extensions import override

from notte_agent.common.base import BaseAgent
from notte_agent.common.conversation import Conversation
from notte_agent.common.perception import BasePerception
from notte_agent.common.prompt import BasePrompt
from notte_agent.common.types import AgentResponse
from notte_agent.common.validator import CompletionValidator
from notte_agent.errors import MaxConsecutiveFailuresError

# #########################################################
# ############### Possible improvements ###################
# #########################################################

# TODO: improve agent memory (e.g. add a memory manager with RAG)
# TODO: use tooling calling for LLM providers that support it
# TODO: file upload/download
# TODO: DIFF rendering module for DOM changes
# TODO: remove base 64 images from current state (reduce token usage)


class NotteAgent(BaseAgent):
    @track_usage("local.agent.create")
    def __init__(
        self,
        prompt: BasePrompt,
        perception: BasePerception,
        config: NotteConfig,
        session: NotteSession,
        trajectory: Trajectory,
        vault: BaseVault | None = None,
    ):
        super().__init__(session=session)
        self.config: NotteConfig = config
        self.llm_tracer: LlmUsageDictTracer = LlmUsageDictTracer()
        self.llm: LLMEngine = LLMEngine(model=self.config.reasoning_model, tracer=self.llm_tracer)
        self.perception: BasePerception = perception
        self.prompt: BasePrompt = prompt
        self.trajectory: Trajectory = trajectory
        self.created_at: dt.datetime = dt.datetime.now()
        self.max_consecutive_failures: int = config.max_consecutive_failures
        self.consecutive_failures: int = 0
        # validator a LLM as a Judge that validates the agent's attempt at completing the task (i.e. `CompletionAction`)
        self.validator: CompletionValidator = CompletionValidator(
            llm=self.llm, perception=self.perception, use_vision=self.config.use_vision
        )

        # ####################################
        # ########### Vault Setup ############
        # ####################################

        # vaults are used to safely input credentials into the sessions without leaking them to the LLM (text + screenshots)
        self.vault: BaseVault | None = vault
        if self.vault is not None:
            # hide vault leaked credentials within llm inputs
            self.llm.structured_completion = self.vault.patch_structured_completion(0, self.vault.get_replacement_map)(  # pyright: ignore [reportAttributeAccessIssue]
                self.llm.structured_completion
            )
            # hide vault leaked credentials within screenshots
            self.session.window.screenshot_mask = VaultSecretsScreenshotMask(vault=self.vault)

    async def action_with_credentials(self, action: BaseAction) -> BaseAction:
        """Replace credentials in the action if the vault contains credentials"""
        if self.vault is not None and self.vault.contains_credentials(action):
            locator = await self.session.locate(action)
            attrs = LocatorAttributes(type=None, autocomplete=None, outerHTML=None)
            if locator is not None:
                # compute locator attributes
                attr_type = await locator.get_attribute("type")
                autocomplete = await locator.get_attribute("autocomplete")
                outer_html = await locator.evaluate("el => el.outerHTML")
                attrs = LocatorAttributes(type=attr_type, autocomplete=autocomplete, outerHTML=outer_html)
                # replace credentials

            if locator is not None or isinstance(action, FormFillAction):
                action = await self.vault.replace_credentials(
                    action,
                    attrs,
                    self.session.snapshot,
                )
        return action

    async def output(self, task: str, answer: str, success: bool) -> AgentResponse:
        return AgentResponse(
            created_at=self.created_at,
            closed_at=dt.datetime.now(),
            answer=answer,
            success=success,
            trajectory=self.trajectory,
            llm_messages=await self.get_messages(task),
            llm_usage=self.llm_tracer.summary(),
        )

    async def observe_and_completion(self, request: AgentRunRequest) -> AgentCompletion:
        _ = await self.session.aobserve(perception_type=self.perception.perception_type)

        # Get messages with the current observation included
        messages = await self.get_messages(request.task)

        with ErrorConfig.message_mode("developer"):
            response: AgentCompletion = await self.llm.structured_completion(
                messages, response_format=AgentCompletion, use_strict_response_format=False
            )

        self.trajectory.append(response, force=True)
        return response

    @profiler.profiled()
    @track_usage("local.agent.step")
    async def step(self, request: AgentRunRequest) -> CompletionAction | None:
        """
        Execute a single step of the agent. The flow is as follows:
        1. Observe the current state of the session
        2. Get the messages with the current observation included
        3. Call the LLM with the messages
        4. Append the LLM response to the trajectory
        5. Execute the action
        6. Append the action result to the trajectory
        7. Return the action result if it is a `CompletionAction`
        """
        response = await self.observe_and_completion(request)

        if self.config.verbose:
            logger.trace(f"🔍 LLM response:\n{response}")
        # log the agent state to the terminal
        response.live_log_state()

        # execute the action
        match response.action:
            case CaptchaSolveAction(captcha_type=captcha_type) if (
                not self.session.window.resource.options.solve_captchas
            ):
                # if the session doesnt solve captchas => fail immediately
                error_msg = f"Agent encountered {captcha_type} captcha but session doesnt solve captchas: create a session with solve_captchas=True"
                ex_res = ExecutionResult(action=response.action, success=False, message=error_msg)
                self.trajectory.append(ex_res, force=True)
                return CompletionAction(success=False, answer=error_msg)

            case CompletionAction(success=False, answer=answer):
                # agent decided to stop with failure
                result = ExecutionResult(action=response.action, success=False, message=answer)
                self.trajectory.append(result, force=True)
                return response.action
            case CompletionAction(success=True, answer=answer) as output:
                # need to validate the agent output
                logger.info(f"🔥 Validating agent output:\n{answer}")
                val_result = await self.validator.validate(
                    output=output,
                    history=self.trajectory,
                    task=request.task,
                    progress=self.progress,
                    response_format=request.response_format,
                )
                if val_result.success:
                    # Successfully validated the output
                    logger.info(f"Validation successful: {val_result.message}")
                    logger.info("✅ Task completed successfully")
                    result = ExecutionResult(action=response.action, success=True, message=val_result.message)
                    self.trajectory.append(result, force=True)
                    # agent and validator agree, stop with success
                    return response.action

                logger.error(f"🚨 Agent validation failed: {val_result.message}. Continuing...")
                agent_failure_msg = (
                    f"Answer validation failed: {val_result.message}. Agent will continue running. "
                    "CRITICAL: If you think this validation is wrong: argue why the task is finished, or "
                    "perform actions that would prove it is."
                )
                result = ExecutionResult(action=response.action, success=False, message=agent_failure_msg)
                self.trajectory.append(result, force=True)
                # disagreement between model and validation, continue
                return None
            case _:
                # The action is a regular action => execute it (default case)
                action = await self.action_with_credentials(response.action)
                result = await self.session.aexecute(action)
                if result.success:
                    self.consecutive_failures = 0
                else:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= self.max_consecutive_failures:
                        # max consecutive failures reached, raise an exception
                        if result.exception is None:
                            result.exception = ValueError(result.message)
                        raise MaxConsecutiveFailuresError(self.max_consecutive_failures) from result.exception
                # Successfully executed the action => add to trajectory
        step_msg = self.perception.perceive_action_result(result, include_ids=True)
        logger.info(f"{step_msg}\n\n")

        return None

    @property
    def progress(self) -> TrajectoryProgress:
        return TrajectoryProgress(current_step=self.trajectory.num_steps, max_steps=self.config.max_steps)

    @track_usage("local.agent.messages.get")
    async def get_messages(self, task: str) -> list[AllMessageValues]:
        """
        Formats a trajectory into a list of messages for the LLM, including the current observation.

        For every resonning model step, the conversation is reset.
        The conversation follows the following format:

        ### Setup messages
        - [system]        : system prompt containing the initial instructions + action tool calls info
        - [user]          : user request task (e.g. "Find the latest news about AI")
        ### Trajectory messages (one for every step in the trajectory)
            - [assistant] : agent step response (containing memory,state & next action to take)
            - [user]      : session step execution result (success/failure + info message)
        ### Current DOM perception & final intent message
        - [user]          : current DOM perception (browser metadata, page DOM elements, interactive actions, etc.)
        - [user]          : final intent message (e.g. "Select the best action based on whatever I gave you in before")

        /!\\ If `use_vision` is enabled, the DOM perception message will contain a screenshot of the page.
        """
        conv: Conversation = Conversation(
            convert_tools_to_assistant=True, autosize=True, model=self.config.reasoning_model
        )
        system_msg, task_msg = self.prompt.system(), self.prompt.task(task)
        if self.vault is not None:
            system_msg += "\n" + self.vault.instructions()
        conv.add_system_message(content=system_msg)
        conv.add_user_message(content=task_msg)

        # otherwise, add all past trajectorysteps to the conversation
        for step in self.trajectory:
            match step:
                case AgentCompletion():
                    # TODO: choose if we want this to be an assistant message or a tool message
                    # self.conv.add_tool_message(step.agent_response, tool_id="step")
                    conv.add_assistant_message(
                        step.model_dump_json(exclude_none=True, context=dict(hide_interactions=True))
                    )
                case ExecutionResult():
                    # add step execution status to the conversation
                    conv.add_user_message(
                        content=self.perception.perceive_action_result(step, include_ids=False, include_data=True)
                    )
                case Observation():
                    # TODO: add partial info for previous?
                    pass

        # Add current observation (only if it's not empty)
        last_obs = self.trajectory.last_observation
        if last_obs is not None and last_obs is not Observation.empty():
            conv.add_user_message(
                content=self.perception.perceive(obs=last_obs, progress=self.progress),
                image=(last_obs.screenshot.bytes() if self.config.use_vision else None),
            )
            conv.add_user_message(self.prompt.select_action())

        # if no action execution in trajectory, add the start trajectory message
        last_exec = self.trajectory.last_result
        if last_exec is None:
            conv.add_user_message(content=self.prompt.empty_trajectory())

        return conv.messages()

    @profiler.profiled()
    @track_usage("local.agent.run")
    @override
    async def arun(self, **data: typing.Unpack[AgentRunRequestDict]) -> AgentResponse:
        request = AgentRunRequest.model_validate(data)
        logger.trace(f"Running task: {request.task}")
        self.consecutive_failures = 0
        self.created_at = dt.datetime.now()
        try:
            with ErrorConfig.message_mode("agent"):
                return await self._run(request)
        except NotteBaseError as e:
            if self.config.raise_condition is RaiseCondition.NEVER:
                return await self.output(
                    request.task, f"Failed due to notte base error: {e.dev_message}:\n{traceback.format_exc()}", False
                )
            logger.error(f"Error during agent run: {e.dev_message}")
            raise e
        except Exception as e:
            if self.config.raise_condition is RaiseCondition.NEVER:
                return await self.output(request.task, f"Failed due to {e}: {traceback.format_exc()}", False)
            raise e
        finally:
            # in case we failed in step, stop it (relevant for session)
            _ = self.trajectory.stop_step(ignore_not_in_step=True)
            _ = self.trajectory.stop()

    async def _run(self, request: AgentRunRequest) -> AgentResponse:
        """Execute the task with maximum number of steps"""
        # change this to DEV if you want more explicit error messages
        # when you are developing your own agent
        if request.url is not None:
            request.task = f"Start on '{request.url}' and {request.task}"

        if self.session.storage is not None:
            request.task = f"{request.task} {self.session.storage.instructions()}"

        # initial goto, don't do an llm call just for accessing the first page
        if request.url is not None:
            _ = self.trajectory.start_step()
            _ = await self.session.aobserve()
            self.trajectory.append(AgentCompletion.initial(request.url), force=True)
            _ = await self.session.aexecute(GotoAction(url=request.url))
            _ = self.trajectory.stop_step()

        step = 0
        while self.trajectory.num_steps < self.config.max_steps:
            step += 1
            logger.info(f"💡 Step {step}")

            _ = self.trajectory.start_step()
            completion_action = await self.step(request)
            _ = self.trajectory.stop_step()

            if completion_action is not None:
                return await self.output(request.task, completion_action.answer, completion_action.success)

        error_msg = f"Failed to solve task in {self.config.max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        return await self.output(request.task, error_msg, False)
