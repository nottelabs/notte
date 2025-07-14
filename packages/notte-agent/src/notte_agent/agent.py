import datetime as dt
import traceback
import typing

import notte_core
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
from notte_core.browser.observation import ExecutionResult, TrajectoryProgress
from notte_core.common.config import NotteConfig, RaiseCondition
from notte_core.common.telemetry import track_usage
from notte_core.common.tracer import LlmUsageDictTracer
from notte_core.credentials.base import BaseVault, LocatorAttributes
from notte_core.errors.base import NotteBaseError
from notte_core.llms.engine import LLMEngine
from notte_core.profiling import profiler
from notte_core.trajectory import Trajectory
from notte_sdk.types import AgentRunRequest, AgentRunRequestDict
from typing_extensions import override

from notte_agent.common.base import BaseAgent
from notte_agent.common.conversation import Conversation
from notte_agent.common.perception import BasePerception
from notte_agent.common.prompt import BasePrompt
from notte_agent.common.safe_executor import SafeActionExecutor
from notte_agent.common.types import AgentResponse
from notte_agent.common.validator import CompletionValidator

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
        self.step_executor: SafeActionExecutor = SafeActionExecutor(session=self.session)
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

        # ####################################
        # ######### Conversation Setup #######
        # ####################################

        self.conversation_args: dict[str, bool | str] = dict(
            convert_tools_to_assistant=True,
            autosize=True,
            model=self.config.reasoning_model,
        )
        self.conv: Conversation = Conversation(**self.conversation_args)  # pyright: ignore [reportArgumentType]
        self.created_at: dt.datetime = dt.datetime.now()

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

    @track_usage("local.agent.reset")
    def reset(self) -> None:
        self.step_executor.reset()
        self.created_at = dt.datetime.now()

    def output(self, answer: str, success: bool) -> AgentResponse:
        return AgentResponse(
            created_at=self.created_at,
            closed_at=dt.datetime.now(),
            answer=answer,
            success=success,
            trajectory=self.trajectory,
            llm_messages=self.conv.messages(),
            llm_usage=self.llm_tracer.summary(),
        )

    @profiler.profiled()
    @track_usage("local.agent.step")
    async def step(self, request: AgentRunRequest) -> CompletionAction | None:
        """Execute a single step of the agent"""

        # Always observe first (added to trajectory)
        _ = await self.session.aobserve(perception_type=self.perception.perception_type)

        # Get messages with the current observation included
        messages = await self.get_messages(request.task)
        with ErrorConfig.message_mode("developer"):
            response: AgentCompletion = await self.llm.structured_completion(
                messages, response_format=AgentCompletion, use_strict_response_format=False
            )
        self.trajectory.append(response, force=True)

        if self.config.verbose:
            logger.trace(f"🔍 LLM response:\n{response}")
        # log the agent state to the terminal
        response.live_log_state()

        action = response.action

        # execute the action
        match action:
            case CaptchaSolveAction() if not self.session.window.resource.options.solve_captchas:
                # if the session doesnt solve captchas => fail immediately
                error_msg = f"Agent encountered {action.captcha_type} captcha but session doesnt solve captchas: create a session with solve_captchas=True"

                async def captcha_failure() -> ExecutionResult:
                    return ExecutionResult(action=action, success=False, message=error_msg)

                # add to trajectory
                _ = await self.session.aexecute_awaitable(captcha_failure())
                return CompletionAction(success=False, answer=error_msg)
            case CompletionAction():

                async def execute_validation() -> ExecutionResult:
                    if not action.success:
                        return ExecutionResult(action=action, success=False, message=action.answer)

                    logger.info(f"🔥 Validating agent output:\n{action.answer}")
                    val_result = await self.validator.validate(
                        output=action,
                        history=self.trajectory,
                        task=request.task,
                        progress=self.progress,
                        response_format=request.response_format,
                    )

                    if val_result.success:
                        # Successfully validated the output
                        logger.info("✅ Task completed successfully")
                        return ExecutionResult(action=action, success=True, message=val_result.message)

                    logger.error(f"🚨 Agent validation failed: {val_result.message}. Continuing...")
                    agent_failure_msg = (
                        f"Answer validation failed: {val_result.message}. Agent will continue running. "
                        "CRITICAL: If you think this validation is wrong: argue why the task is finished, or "
                        "perform actions that would prove it is."
                    )
                    return ExecutionResult(action=action, success=False, message=agent_failure_msg)

                session_step = await self.session.aexecute_awaitable(execute_validation())

                # stop right there if agent and validator agree on the result
                if (action.success and session_step.success) or not action.success:
                    return action

                return None

            case _:
                # The action is a regular action => execute it (default case)
                action = await self.action_with_credentials(response.action)
                session_step = await self.step_executor.execute(action)

        # Successfully executed the action => add to trajectory
        step_msg = self.perception.perceive_action_result(session_step, include_ids=True)
        logger.info(f"{step_msg}\n\n")

        return None

    @property
    def progress(self) -> TrajectoryProgress:
        return TrajectoryProgress(current_step=self.trajectory.num_steps, max_steps=self.config.max_steps)

    @track_usage("local.agent.messages.get")
    async def get_messages(self, task: str) -> list[AllMessageValues]:
        self.conv = Conversation.from_trajectory(
            self.trajectory,
            self.perception,
            self.prompt,
            task,
            self.vault,
            self.config.use_vision,
            self.config.max_steps,
        )
        return self.conv.messages()

    @profiler.profiled()
    @track_usage("local.agent.run")
    @override
    async def run(self, **data: typing.Unpack[AgentRunRequestDict]) -> AgentResponse:
        request = AgentRunRequest.model_validate(data)
        logger.trace(f"Running task: {request.task}")
        self.created_at = dt.datetime.now()
        try:
            return await self._run(request)
        except NotteBaseError as e:
            if self.config.raise_condition is RaiseCondition.NEVER:
                return self.output(f"Failed due to notte base error: {e.dev_message}:\n{traceback.format_exc()}", False)
            logger.error(f"Error during agent run: {e.dev_message}")
            raise e
        except Exception as e:
            if self.config.raise_condition is RaiseCondition.NEVER:
                return self.output(f"Failed due to {e}: {traceback.format_exc()}", False)
            raise e
        finally:
            # in case we failed in step, stop it (relevant for session)
            _ = self.trajectory.stop_step(ignore_not_in_step=True)
            _ = self.trajectory.stop()

    async def _run(self, request: AgentRunRequest) -> AgentResponse:
        """Execute the task with maximum number of steps"""
        # change this to DEV if you want more explicit error messages
        # when you are developing your own agent
        notte_core.set_error_mode("agent")
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
                return self.output(completion_action.answer, completion_action.success)

        error_msg = f"Failed to solve task in {self.config.max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        notte_core.set_error_mode("developer")
        return self.output(error_msg, False)
