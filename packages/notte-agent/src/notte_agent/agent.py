import datetime as dt
import traceback
import typing
from collections.abc import Callable

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
)
from notte_core.agent_types import AgentStepResponse
from notte_core.common.config import NotteConfig, RaiseCondition
from notte_core.common.telemetry import track_usage
from notte_core.common.tracer import LlmUsageDictTracer
from notte_core.credentials.base import BaseVault, LocatorAttributes
from notte_core.errors.base import NotteBaseError
from notte_core.llms.engine import LLMEngine
from notte_core.profiling import profiler
from notte_sdk.types import AgentRunRequest, AgentRunRequestDict
from typing_extensions import override

from notte_agent.common.base import BaseAgent
from notte_agent.common.conversation import Conversation
from notte_agent.common.perception import BasePerception
from notte_agent.common.prompt import BasePrompt
from notte_agent.common.safe_executor import SafeActionExecutor
from notte_agent.common.trajectory_history import AgentTrajectoryHistory
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
        vault: BaseVault | None = None,
        step_callback: Callable[[AgentStepResponse], None] | None = None,
    ):
        super().__init__(session=session)
        self.config: NotteConfig = config
        self.llm_tracer: LlmUsageDictTracer = LlmUsageDictTracer()
        self.llm: LLMEngine = LLMEngine(model=self.config.reasoning_model, tracer=self.llm_tracer)
        self.perception: BasePerception = perception
        self.prompt: BasePrompt = prompt
        self.step_callback: Callable[[AgentStepResponse], None] | None = step_callback
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

        self.conv: Conversation = Conversation(
            convert_tools_to_assistant=True,
            autosize=True,
            model=self.config.reasoning_model,
        )
        self.trajectory: AgentTrajectoryHistory = AgentTrajectoryHistory(max_steps=self.config.max_steps)
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
        self.conv.reset()
        self.trajectory.reset()
        self.step_executor.reset()
        self.created_at = dt.datetime.now()

    def output(self, answer: str, success: bool) -> AgentResponse:
        return AgentResponse(
            created_at=self.created_at,
            closed_at=dt.datetime.now(),
            answer=answer,
            success=success,
            trajectory=self.trajectory.steps,
            llm_messages=self.conv.messages(),
            llm_usage=self.llm_tracer.summary(),
        )

    @track_usage("local.agent.messages.get")
    async def get_messages(self, task: str) -> list[AllMessageValues]:
        """
        Formats a trajectory into a list of messages for the LLM.

        For every resonning model step, the conversation is reset.
        The conversation follows the following format:

        ### Setup messages
        - [system]        : system prompt containing the initial instructions + action tool calls info
        - [user]          : user request task (e.g. "Find the latest news about AI")
        ### Trajectory messages (one for every step in the trajectory)
            - [assistant] : agent step response (containing memory,state & next action to take)
            - [user]      : session step execution result (success/failure + info message)
        ### DOM perception & final intent message
        - [user]          : DOM perception (browser metadata, page DOM elements, interactive actions, etc.)
        - [user]          : final intent message (e.g. "Select the best action based on whatever I gave you in before")

        /!\\ If `use_vision` is enabled, the DOM perception message will contain a screenshot of the page.
        """
        self.conv.reset()
        system_msg, task_msg = self.prompt.system(), self.prompt.task(task)
        if self.vault is not None:
            system_msg += "\n" + self.vault.instructions()
        self.conv.add_system_message(content=system_msg)
        self.conv.add_user_message(content=task_msg)
        # if no steps in trajectory, add the start trajectory message
        if len(self.trajectory.steps) == 0:
            self.conv.add_user_message(content=self.prompt.empty_trajectory())
            return self.conv.messages()
        # otherwise, add all past trajectorysteps to the conversation
        for step in self.trajectory.steps:
            # TODO: choose if we want this to be an assistant message or a tool message
            # self.conv.add_tool_message(step.agent_response, tool_id="step")
            step_json = step.agent_response.model_dump_json(exclude_none=True)
            self.conv.add_assistant_message(step_json)
            # add step execution status to the conversation
            step_result_content = self.perception.perceive_action_result(
                step.action, step.result, include_ids=False, include_data=True
            )
            self.conv.add_user_message(content=step_result_content)
            # NOTE: if you want to include the full observation (not only structured data), you can do it like this:
            # self.conv.add_user_message(
            #     content=self.perception.perceive(obs),
            #     image=(obs.screenshot if self.config.use_vision else None),
            # )
        last_obs = self.trajectory.last_obs()
        self.conv.add_user_message(
            content=self.perception.perceive(last_obs),
            image=(last_obs.screenshot.bytes() if self.config.use_vision else None),
        )
        self.conv.add_user_message(self.prompt.select_action())
        return self.conv.messages()

    @profiler.profiled()
    @track_usage("local.agent.step")
    async def step(self, request: AgentRunRequest) -> CompletionAction | None:
        """Execute a single step of the agent"""
        messages = await self.get_messages(request.task)
        response: AgentStepResponse = await self.llm.structured_completion(
            messages, response_format=AgentStepResponse, use_strict_response_format=False
        )

        if self.step_callback is not None:
            self.step_callback(response)

        if self.config.verbose:
            logger.trace(f"🔍 LLM response:\n{response}")
        # log the agent state to the terminal
        response.live_log_state()

        # execute the action
        match response.action:
            case CaptchaSolveAction() if not self.session.window.resource.options.solve_captchas:
                # if the session doesnt solve captchas => fail immediately
                error_msg = f"Agent encountered {response.action.captcha_type} captcha but session doesnt solve captchas: create a session with solve_captchas=True"
                return CompletionAction(success=False, answer=error_msg)
            case CompletionAction(success=False, answer=answer):
                # agent failed to complete the task => fail immediately
                logger.error(f"🚨 Agent terminated early with failure: {answer}")
                return CompletionAction(success=False, answer=answer)
            case CompletionAction(success=True, answer=answer):
                # Sucessful execution and need to validate the output
                logger.info(f"🔥 Validating agent output:\n{answer}")
                val_result = await self.validator.validate(
                    output=response.action,
                    history=self.trajectory,
                    task=request.task,
                    response_format=request.response_format,
                )
                if val_result.success:
                    # Successfully validated the output
                    logger.info("✅ Task completed successfully")
                    return response.action
                logger.error(f"🚨 Agent validation failed: {val_result.message}. Continuing...")
                agent_failure_msg = f"""Answer validation failed: {val_result.message}. Continuing...
                CRITICAL: If you think this validation is wrong: argue why the task is finished, or
                perform actions that would prove it is.
                """
                # make sure to add the
                session_step = await self.step_executor.fail(response.action, agent_failure_msg)
            case _:
                # The action is a regular action => execute it (default case)
                action_with_credentials = await self.action_with_credentials(response.action)
                session_step = await self.step_executor.execute(action_with_credentials)
        # Successfully executed the action => add to trajectory
        self.trajectory.add_step(response, session_step)
        step_msg = self.perception.perceive_action_result(response.action, session_step.result, include_ids=True)
        logger.info(f"{step_msg}\n\n")
        return None

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

    async def _run(self, request: AgentRunRequest) -> AgentResponse:
        """Execute the task with maximum number of steps"""
        # change this to DEV if you want more explicit error messages
        # when you are developing your own agent
        notte_core.set_error_mode("agent")
        if request.url is not None:
            request.task = f"Start on '{request.url}' and {request.task}"

        if self.session.storage is not None:
            request.task = f"{request.task} {self.session.storage.instructions()}"

        for step in range(self.config.max_steps):
            logger.info(f"💡 Step {step}")
            completion_action = await self.step(request)
            if completion_action is not None:
                return self.output(completion_action.answer, completion_action.success)

        error_msg = f"Failed to solve task in {self.config.max_steps} steps"
        logger.info(f"🚨 {error_msg}")
        notte_core.set_error_mode("developer")
        return self.output(error_msg, False)
