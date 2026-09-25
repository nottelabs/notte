import json
import re
import typing
from collections import Counter
from typing import Any, Literal

from litellm import AllMessageValues
from notte_browser.session import NotteSession
from notte_browser.tools.base import BaseTool
from notte_core.actions import (
    BaseAction,
    CheckAction,
    ClickAction,
    CompletionAction,
    FillAction,
    GoBackAction,
    GotoAction,
    InteractionAction,
    PressKeyAction,
    ReloadAction,
    ScrapeAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    WaitAction,
)
from notte_core.agent_types import AgentCompletion, AgentState, RelevantInteraction
from notte_core.browser.observation import Observation
from notte_core.common.logging import logger
from notte_core.credentials.base import BaseVault
from notte_core.errors.base import ErrorConfig, NotteBaseError
from notte_core.trajectory import Trajectory
from notte_llm.decision import (
    DEFAULT_DECISION_MODEL,
    MAX_CHOICE_OPTIONS,
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionEngine,
    DecisionModelError,
    DecisionQuestion,
    NoulQuestion,
)
from notte_llm.engine import LLMEngine
from notte_sdk.types import AgentCreateRequestDict, AgentRunRequest
from pydantic import BaseModel
from typing_extensions import override

from notte_agent.common.types import AgentResponse
from notte_agent.common.validator import BaseValidator, CompletionValidator
from notte_agent.falco.agent import FalcoAgent
from notte_agent.jev.validator import DecisionValidator

NEXT_INSTRUCTIONS = (
    "A web browsing agent must complete `task`. Given `previous_actions` and the current `page`, "
    "which single action should it take next? When several actions are still required (e.g. multiple form fields), "
    "select the one that comes first on the page. Only submit or search once every value required by `task` is set."
)
DONE_INSTRUCTIONS = "The task is fully completed given `previous_actions` and the current `page`"
VALUE_INSTRUCTIONS = "Which value should the web browsing agent provide for `action` to make progress on `task`?"
NO_VALUE = "NONE_OF_THESE"
OTHER = "other"
COMPLETION = "completion"
MAX_HISTORY_ACTIONS = 15
MAX_VALUE_CANDIDATES = 20
MAX_RECENT_ACTIONS = 6
# the decision model is paused after too many low confidence steps in a row (i.e. the website is too ambiguous for it)
MAX_CONSECUTIVE_LOW_CONFIDENCE = 3
NB_PAUSED_STEPS = 5
# decision models have a small context window (32k tokens, ~2 chars per token on html heavy inputs)
MAX_DECISION_INPUT_CHARS = 60_000

TASK_VALUES_PROMPT = """List every literal value of the following task that may have to be typed or selected
in a web page to complete it (e.g. names, places, dates, quantities, search queries, etc.).
Copy the values verbatim from the task, one entry per value, without any explanation.

Task: """

PARAMETERS_SYSTEM_PROMPT = """You are part of a web browsing agent. The next action to take has already been selected.
Your only job is to provide the missing parameters of this action so that it makes progress on the task.
Be concise, don't explain yourself, and only use information from the task, the history or the current page."""

TParameter = typing.TypeVar("TParameter", bound=BaseModel)


class ValueParameter(BaseModel):
    value: str


class TaskValues(BaseModel):
    values: list[str]


class CheckParameter(BaseModel):
    value: bool


class GotoParameter(BaseModel):
    url: str


class ScrapeParameter(BaseModel):
    instructions: str


class CompletionParameter(BaseModel):
    success: bool
    answer: str


class ActionOption(BaseModel):
    """One entry of the flattened action space: a fully specified action, except for its parameters"""

    description: str
    action_type: str
    id: str | None = None
    key: str | None = None


def browser_options(obs: Observation) -> dict[str, ActionOption]:
    options = {
        "goto(url)": ActionOption(
            action_type="goto",
            description="Navigate to another URL, e.g. when the URL is known or can be derived from the current one",
        ),
        "scrape(instructions)": ActionOption(
            action_type="scrape",
            description="Extract data from the current page when the needed information is not readable in `page`",
        ),
        "go_back()": ActionOption(
            action_type="go_back", description="The current page is a dead end or the wrong page: go back"
        ),
        "reload()": ActionOption(action_type="reload", description="The page looks broken or stale: reload it"),
        "wait()": ActionOption(action_type="wait", description="The page is still loading: wait for a moment"),
        COMPLETION: ActionOption(
            action_type="completion",
            description="The task is already fully completed (or impossible): stop and return the answer",
        ),
        OTHER: ActionOption(
            action_type="other",
            description="Something else: solve a captcha, switch or close tabs, read emails or sms, fill a whole form",
        ),
    }
    for key in ("Enter", "Escape", "Tab"):
        options[f"press_key({key})"] = ActionOption(
            action_type="press_key", key=key, description=f"Press the '{key}' keyboard key"
        )
    if obs.metadata.viewport.pixels_below > 0:
        options["scroll_down()"] = ActionOption(
            action_type="scroll_down",
            description="None of the visible elements is the right one yet: scroll down to reveal more of the page",
        )
    if obs.metadata.viewport.pixels_above > 0:
        options["scroll_up()"] = ActionOption(
            action_type="scroll_up", description="The needed element is above the current view: scroll up"
        )
    return options


def effective_action_type(action: InteractionAction) -> str:
    """
    Comboboxes are typed as `select_dropdown_option`, but only native `<select>` elements can be handled this way:
    - text inputs with suggestions (e.g. autocomplete) have to be filled
    - custom dropdowns and their options have to be clicked
    """
    if action.type != "select_dropdown_option":
        return action.type
    html = action.description.lstrip()
    if html.startswith("<select"):
        return "select_dropdown_option"
    if html.startswith("<input") and not action.id.startswith("O"):
        return "fill"
    return "click"


def flatten_action_space(obs: Observation) -> dict[str, ActionOption]:
    """Flattened action space: one option per (action, element) pair + the browser actions"""
    options: dict[str, ActionOption] = {}
    for action in obs.space.interaction_actions:
        action_type = effective_action_type(action)
        param = ", value" if action_type in ("fill", "select_dropdown_option", "check") else ""
        options[f"{action_type}(id={action.id}{param})"] = ActionOption(
            action_type=action_type,
            id=action.id,
            description=f"{action.text_label or ''!r} {action.description[:160]}",
        )
    return {**options, **browser_options(obs)}


def value_candidates(task: str) -> list[str]:
    """Values that are explicitly given within the task (i.e. quoted text)"""
    quoted: list[tuple[str, str]] = re.findall(r"'([^'\n]{1,80})'|\"([^\"\n]{1,80})\"", task)
    candidates = [single or double for single, double in quoted]
    # urls are never typed into a field (the task is prefixed with the start url)
    candidates = [candidate for candidate in candidates if not candidate.startswith(("http://", "https://"))]
    return list(dict.fromkeys(candidates))[:MAX_VALUE_CANDIDATES]


class JevAgent(FalcoAgent):
    """
    Hybrid agent: a decision model (i.e. TypeSafe Jev) picks the next action out of a flattened action space
    (e.g. `click(id=B1)`, `fill(id=I1, value)`, `goto(url)`, `scroll_down()`, `completion`, etc.).

    Decision models don't generate text: they select *which* action to take, along with a probability for every
    candidate, but they can't produce action parameters (fill values, urls, answers, etc.). Hence:
    - parameter-free actions are executed directly (no LLM call).
    - missing parameters are either selected by the decision model (when the value is given in the task),
      or generated by a small and focused LLM call (no reasoning, no action selection).
    - the regular reasoning LLM step is only used when the decision model shouldn't decide on its own
      (low confidence, previous action failed, unsupported action, action space too large).
    """

    def __init__(
        self,
        session: NotteSession,
        vault: BaseVault | None = None,
        tools: list[BaseTool] | None = None,
        trajectory: Trajectory | None = None,
        decision_model: str = DEFAULT_DECISION_MODEL,
        confidence_threshold: float = 0.6,
        parameter_model: str | None = None,
        **data: typing.Unpack[AgentCreateRequestDict],
    ):
        super().__init__(session=session, vault=vault, tools=tools, trajectory=trajectory, **data)
        # action parameters are short and easy to generate: a small & fast model can be used instead of the reasoning one
        self.parameter_llm: LLMEngine | None = None
        if parameter_model is not None:
            self.parameter_llm = LLMEngine(model=parameter_model, tracer=self.llm_tracer)
            if self.vault is not None:
                self.parameter_llm.structured_completion = self.vault.patch_structured_completion(  # pyright: ignore [reportAttributeAccessIssue]
                    0, self.vault.get_replacement_map
                )(self.parameter_llm.structured_completion)
        self.decision: DecisionEngine = DecisionEngine(model=decision_model)
        self.confidence_threshold: float = confidence_threshold
        # step counts to keep track of how often the reasoning LLM is actually bypassed
        self.nb_decision_steps: int = 0
        self.nb_parameter_llm_calls: int = 0
        self.fallback_reasons: Counter[str] = Counter()
        self.nb_consecutive_low_confidence: int = 0
        self.nb_paused_steps: int = 0
        self.task_values: list[str] | None = None
        # the LLM validator is only used if the decision model is not confident that the answer is valid
        llm_validator = CompletionValidator(llm=self.llm, perception=self.perception, use_vision=self.config.use_vision)
        self.validator: BaseValidator = DecisionValidator(
            decision=self.decision, llm_validator=llm_validator, perception=self.perception
        )

    # ############################################
    # ######### Decision model inputs ############
    # ############################################

    def _previous_actions(self, include_data: bool = False) -> list[str]:
        results = list(self.trajectory.execution_results())[-MAX_HISTORY_ACTIONS:]
        return [
            self.perception.perceive_action_result(result, include_ids=True, include_data=include_data)
            for result in results
        ]

    def _state(self, request: AgentRunRequest, obs: Observation) -> dict[str, Any]:
        return {
            "task": request.task,
            "previous_actions": self._previous_actions() or "none yet",
            "current_url": obs.metadata.url,
            "page_title": obs.metadata.title,
            "pixels_below_viewport": obs.metadata.viewport.pixels_below,
        }

    def _mask_credentials(self, data: Any) -> Any:
        # hide vault leaked credentials within decision model inputs
        if self.vault is None:
            return data
        return BaseVault.recursive_replace_mapping(data, self.vault.get_replacement_map())

    async def _decide(
        self, request: AgentRunRequest, obs: Observation, options: dict[str, ActionOption]
    ) -> tuple[ChoiceAnswer, float] | None:
        questions: dict[str, DecisionQuestion] = {
            "next": ChoiceQuestion(
                instructions=NEXT_INSTRUCTIONS,
                criteria=self._mask_credentials({key: option.description for key, option in options.items()}),
            ),
            "done": NoulQuestion(instructions=DONE_INSTRUCTIONS),
        }
        state = self._mask_credentials(self._state(request, obs))
        nb_chars = len(json.dumps(state)) + sum(len(q.model_dump_json()) for q in questions.values())
        if nb_chars > MAX_DECISION_INPUT_CHARS:
            return None
        # the page content is what helps to disambiguate similar elements: include as much as the context allows
        state["page"] = self._mask_credentials(obs.space.description)[: MAX_DECISION_INPUT_CHARS - nb_chars]
        response = await self.decision.decide(state=state, questions=questions)
        return response.choice("next"), response.noul("done")

    # ############################################
    # ########### Action parameters ##############
    # ############################################

    async def _task_values(self, request: AgentRunRequest) -> list[str]:
        """Values given in the task: extracted once by the LLM so that the decision model can select them afterwards"""
        if self.task_values is None:
            candidates: list[str] = []
            try:
                self.nb_parameter_llm_calls += 1
                messages: list[AllMessageValues] = [{"role": "user", "content": TASK_VALUES_PROMPT + request.task}]
                with ErrorConfig.message_mode("developer"):
                    llm = self.parameter_llm or self.llm
                    extracted = await llm.structured_completion(messages, response_format=TaskValues)
                # only keep verbatim values: the decision model should never type something the LLM made up
                candidates = [value for value in extracted.values if value in request.task and len(value) <= 80]
            except NotteBaseError as e:
                logger.warning(f"🎲 Failed to extract the task values: {e.dev_message}")
            self.task_values = [c for c in dict.fromkeys(candidates) if not c.startswith("http")][:MAX_VALUE_CANDIDATES]
            logger.info(f"🎲 Task values: {self.task_values}")
        return self.task_values

    async def _pick_value(
        self, request: AgentRunRequest, option_key: str, option: ActionOption, candidates: list[str]
    ) -> str | None:
        criteria = {candidate: "value given in the task" for candidate in candidates}
        criteria[NO_VALUE] = "None of the other values is the right one: the value has to be written from scratch"
        state = {
            "task": request.task,
            "previous_actions": self._previous_actions() or "none yet",
            "action": f"{option_key}: {option.description}",
        }
        question = ChoiceQuestion(instructions=VALUE_INSTRUCTIONS, criteria=criteria)
        response = await self.decision.decide(state=state, questions={"value": question})
        answer = response.choice("value")
        logger.info(f"🎲 Decision model value: {answer.top(3)} (confidence={answer.confidence:.2f})")
        if answer.choice == NO_VALUE or answer.confidence < self.confidence_threshold:
            return None
        return answer.choice

    async def _select_value(self, request: AgentRunRequest, option_key: str, option: ActionOption) -> str | None:
        """Let the decision model pick the value if it is explicitly given in the task"""
        if self.vault is not None:
            return None
        # quoted values don't require any LLM call
        quoted = value_candidates(request.task)
        if len(quoted) > 0:
            value = await self._pick_value(request, option_key, option, quoted)
            if value is not None:
                return value
        candidates = [value for value in await self._task_values(request) if value not in quoted]
        if len(candidates) == 0:
            return None
        return await self._pick_value(request, option_key, option, candidates)

    def _parameter_messages(
        self, request: AgentRunRequest, obs: Observation, option_key: str, option: ActionOption
    ) -> list[AllMessageValues]:
        system = PARAMETERS_SYSTEM_PROMPT
        if self.vault is not None:
            system += "\n" + self.vault.instructions()
        task = request.task
        if request.response_format is not None and "response format" not in task:
            schema = json.dumps(request.response_format.model_json_schema())
            task = f"{task}\nUse the following response format to format your answer:\n```json\n{schema}\n```"
        last_completion = self.trajectory.last_completion
        memory = last_completion.state.memory if last_completion is not None else "No memory yet"
        history = "\n".join(self._previous_actions(include_data=True)) or "none yet"
        content = f"""# Task
{task}

# Memory
{memory}

# Previous actions
{history}

# Current page
{self.perception.perceive(obs=obs, progress=self.progress)}

# Selected action
{option_key}: {option.description}

Provide the missing parameters of the selected action."""
        return [{"role": "system", "content": system}, {"role": "user", "content": content}]

    async def _generate(
        self,
        response_format: type[TParameter],
        request: AgentRunRequest,
        obs: Observation,
        option_key: str,
        option: ActionOption,
    ) -> TParameter:
        self.nb_parameter_llm_calls += 1
        messages = self._parameter_messages(request, obs, option_key, option)
        with ErrorConfig.message_mode("developer"):
            llm = self.parameter_llm or self.llm
            return await llm.structured_completion(messages, response_format=response_format)

    async def _build_action(
        self, request: AgentRunRequest, obs: Observation, option_key: str, option: ActionOption
    ) -> BaseAction | None:
        """Returns None if the action is not supported by the decision model path"""
        match option.action_type:
            case "click" if option.id is not None:
                return ClickAction(id=option.id)
            case "scroll_down":
                return ScrollDownAction()
            case "scroll_up":
                return ScrollUpAction()
            case "go_back":
                return GoBackAction()
            case "reload":
                return ReloadAction()
            case "wait":
                return WaitAction(time_ms=1000)
            case "press_key" if option.key is not None:
                return PressKeyAction(key=option.key)
            case "fill" | "select_dropdown_option" if option.id is not None:
                value = await self._select_value(request, option_key, option)
                if value is None:
                    value = (await self._generate(ValueParameter, request, obs, option_key, option)).value
                if option.action_type == "fill":
                    return FillAction(id=option.id, value=value)
                return SelectDropdownOptionAction(id=option.id, value=value)
            case "check" if option.id is not None:
                check = await self._generate(CheckParameter, request, obs, option_key, option)
                return CheckAction(id=option.id, value=check.value)
            case "goto":
                return GotoAction(url=(await self._generate(GotoParameter, request, obs, option_key, option)).url)
            case "scrape":
                scrape = await self._generate(ScrapeParameter, request, obs, option_key, option)
                return ScrapeAction(instructions=scrape.instructions)
            case "completion":
                completion = await self._generate(CompletionParameter, request, obs, option_key, option)
                return CompletionAction(success=completion.success, answer=completion.answer)
            case _:
                return None

    # ############################################
    # ############# Agent completion #############
    # ############################################

    def _is_repeated(self, option: ActionOption) -> bool:
        """
        The decision model doesn't see the effect of its actions: repeating an action that was already taken recently
        (including cycles, e.g. fill -> press_key -> fill -> etc.) means that it is stuck => let the LLM reason.
        """
        if option.action_type in ("scroll_down", "scroll_up", "wait", "goto", "scrape", "completion"):
            # scrolling / waiting multiple times in a row is fine, and the others depend on their parameters
            return False

        def signature(action: BaseAction) -> tuple[str, str | None]:
            if isinstance(action, InteractionAction):
                return action.type, action.id
            return action.type, action.key if isinstance(action, PressKeyAction) else None

        target = (option.action_type, option.id or option.key)
        recent = [signature(completion.action) for completion in self.trajectory.agent_completions()]
        recent = recent[-MAX_RECENT_ACTIONS:]
        if option.id is not None:
            # the same element can legitimately be used twice (e.g. 'next' page), but not back to back
            return (len(recent) > 0 and recent[-1] == target) or recent.count(target) >= 2
        return recent.count(target) >= 1

    def _agent_state(self, obs: Observation, answer: ChoiceAnswer, options: dict[str, ActionOption]) -> AgentState:
        last_result, last_completion = self.trajectory.last_result, self.trajectory.last_completion
        status: Literal["success", "failure", "unknown"] = "unknown"
        if last_result is not None:
            status = "success" if last_result.success else "failure"
        relevant = [(options[key].id, prob) for key, prob in answer.top(3) if key in options and prob > 0]
        return AgentState(
            previous_goal_status=status,
            previous_goal_eval=f"Previous action status: {status}",
            page_summary=f"{obs.metadata.title} ({obs.metadata.url})",
            relevant_interactions=[
                RelevantInteraction(id=element_id, reason=f"decision model probability: {prob:.2f}")
                for element_id, prob in relevant
                if element_id is not None
            ],
            # the decision model has no memory: carry over the one from the last LLM step
            memory=last_completion.state.memory if last_completion is not None else "No memory yet",
            next_goal=f"{answer.choice} (selected by decision model with confidence {answer.confidence:.2f})",
        )

    async def _fallback(self, request: AgentRunRequest, reason: str) -> AgentCompletion.InnerLlmCompletion:
        self.fallback_reasons[reason] += 1
        if reason == "low confidence":
            self.nb_consecutive_low_confidence += 1
            if self.nb_consecutive_low_confidence >= MAX_CONSECUTIVE_LOW_CONFIDENCE:
                # still uncertain after the pause => pause again right away
                self.nb_paused_steps = NB_PAUSED_STEPS
        logger.info(f"🧠 Decision model fallback to LLM: {reason}")
        return await super().completion(request)

    @override
    async def completion(self, request: AgentRunRequest) -> AgentCompletion.InnerLlmCompletion:
        obs = self.trajectory.last_observation
        if obs is None or obs.space.is_empty():
            return await self._fallback(request, "empty action space")
        last_result = self.trajectory.last_result
        if last_result is not None and not last_result.success:
            # let the LLM reason about failures
            return await self._fallback(request, "previous action failed")
        if self.nb_paused_steps > 0:
            self.nb_paused_steps -= 1
            return await self._fallback(request, "decision model paused")
        options = flatten_action_space(obs)
        if len(options) > MAX_CHOICE_OPTIONS:
            return await self._fallback(request, "too many actions")

        try:
            decision = await self._decide(request, obs, options)
            if decision is None:
                return await self._fallback(request, "action space too large")
            answer, done = decision
            logger.info(f"🎲 Decision model: {answer.top(3)} (confidence={answer.confidence:.2f}, done={done:.2f})")
            if answer.choice == COMPLETION:
                # the completion is validated afterwards: trust either of the two signals
                if max(answer.confidence, done) < self.confidence_threshold:
                    return await self._fallback(request, "low confidence")
            elif answer.confidence < self.confidence_threshold:
                return await self._fallback(request, "low confidence")
            elif done >= self.confidence_threshold:
                return await self._fallback(request, "conflicting completion signal")
            option = options[answer.choice]
            if self._is_repeated(option):
                return await self._fallback(request, "repeated action")
            action = await self._build_action(request, obs, answer.choice, option)
        except DecisionModelError as e:
            logger.warning(f"🎲 {e.dev_message}")
            return await self._fallback(request, "decision model error")
        except NotteBaseError as e:
            logger.warning(f"🎲 Failed to generate action parameters: {e.dev_message}")
            return await self._fallback(request, "parameters error")

        if action is None:
            return await self._fallback(request, f"unsupported action: {option.action_type}")
        last_completion = self.trajectory.last_completion
        if isinstance(action, GotoAction) and last_completion is not None and last_completion.action == action:
            return await self._fallback(request, "repeated action")

        self.nb_decision_steps += 1
        self.nb_consecutive_low_confidence = 0
        return AgentCompletion.InnerLlmCompletion(state=self._agent_state(obs, answer, options), action=action)

    @override
    async def _run(self, request: AgentRunRequest) -> AgentResponse:
        try:
            return await super()._run(request)
        finally:
            nb_fallbacks = sum(self.fallback_reasons.values())
            stats = (
                f"{self.nb_decision_steps} decision steps ({self.nb_parameter_llm_calls} parameter LLM calls), "
                f"{nb_fallbacks} LLM fallbacks {dict(self.fallback_reasons)}"
            )
            logger.info(f"🎲 Decision model stats: {stats}, cost=${self.decision.usage.cost:.5f}")
