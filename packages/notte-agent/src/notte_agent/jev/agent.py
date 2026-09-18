import typing
from collections import Counter
from typing import Any, Literal

from notte_browser.session import NotteSession
from notte_browser.tools.base import BaseTool
from notte_core.actions import BaseAction, ClickAction, GoBackAction, InteractionAction, ScrollDownAction
from notte_core.agent_types import AgentCompletion, AgentState, RelevantInteraction
from notte_core.browser.observation import Observation
from notte_core.common.logging import logger
from notte_core.credentials.base import BaseVault
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
from notte_sdk.types import AgentCreateRequestDict, AgentRunRequest
from typing_extensions import override

from notte_agent.common.types import AgentResponse
from notte_agent.falco.agent import FalcoAgent

SCROLL_DOWN = "SCROLL_DOWN"
GO_BACK = "GO_BACK"
OTHER = "OTHER"
DONE = "DONE"

SPECIAL_OPTIONS: dict[str, str] = {
    SCROLL_DOWN: "None of the visible elements is the right one yet: scroll down to reveal more of the page",
    GO_BACK: "The current page is a dead end or the wrong page: go back to the previous page",
    OTHER: (
        "Something else is needed: navigate to a URL, extract data from the page, wait, solve a captcha, "
        "press a key, switch tab, etc."
    ),
    DONE: "The task is already fully completed given `previous_actions` and the current `page`",
}
NEXT_INSTRUCTIONS = (
    "A web browsing agent must complete `task`. Given `previous_actions` and the current `page`, "
    "which single action should it take next?"
)
DONE_INSTRUCTIONS = "The task is fully completed given `previous_actions` and the current `page`"
MAX_HISTORY_ACTIONS = 15


class JevAgent(FalcoAgent):
    """
    Hybrid agent: a decision model (i.e. TypeSafe Jev) picks the next action out of the action space, and the
    reasoning LLM is only used when the decision model can't / shouldn't decide on its own.

    Decision models don't generate text. They can select *which* action to take, along with a probability for every
    candidate, but they can't produce action parameters (fill values, urls, answers, etc.). Hence:
    - parameter-free actions selected with high confidence (click, scroll down, go back) are executed directly.
    - everything else (low confidence, parameters required, task completion, failures) falls back to the LLM.
    """

    def __init__(
        self,
        session: NotteSession,
        vault: BaseVault | None = None,
        tools: list[BaseTool] | None = None,
        trajectory: Trajectory | None = None,
        decision_model: str = DEFAULT_DECISION_MODEL,
        confidence_threshold: float = 0.8,
        **data: typing.Unpack[AgentCreateRequestDict],
    ):
        super().__init__(session=session, vault=vault, tools=tools, trajectory=trajectory, **data)
        self.decision: DecisionEngine = DecisionEngine(model=decision_model)
        self.confidence_threshold: float = confidence_threshold
        # step counts to keep track of how often the LLM is actually bypassed
        self.nb_decision_steps: int = 0
        self.fallback_reasons: Counter[str] = Counter()

    def _previous_actions(self) -> list[str]:
        results = list(self.trajectory.execution_results())[-MAX_HISTORY_ACTIONS:]
        return [
            self.perception.perceive_action_result(result, include_ids=True, include_data=False) for result in results
        ]

    def _questions(self, obs: Observation) -> dict[str, DecisionQuestion]:
        criteria = {
            action.id: f"{action.type} {action.text_label or ''!r} {action.description[:160]}"
            for action in obs.space.interaction_actions
        }
        return {
            "next": ChoiceQuestion(instructions=NEXT_INSTRUCTIONS, criteria={**criteria, **SPECIAL_OPTIONS}),
            "done": NoulQuestion(instructions=DONE_INSTRUCTIONS),
        }

    def _state(self, request: AgentRunRequest, obs: Observation) -> dict[str, Any]:
        return {
            "task": request.task,
            "previous_actions": self._previous_actions() or "none yet",
            "current_url": obs.metadata.url,
            "page_title": obs.metadata.title,
            "pixels_below_viewport": obs.metadata.viewport.pixels_below,
            "page": obs.space.description,
        }

    def _select_action(self, obs: Observation, answer: ChoiceAnswer) -> BaseAction | None:
        """Returns the selected action if it can be executed without any LLM-generated parameter"""
        if answer.choice == SCROLL_DOWN:
            return ScrollDownAction() if obs.metadata.viewport.pixels_below > 0 else None
        if answer.choice == GO_BACK:
            return GoBackAction()
        selected = next((a for a in obs.space.interaction_actions if a.id == answer.choice), None)
        # OTHER, DONE and interactions with parameters (fill, select, etc.) can't be handled without the LLM
        return ClickAction(id=selected.id) if isinstance(selected, ClickAction) else None

    def _is_repeated(self, action: BaseAction) -> bool:
        last = self.trajectory.last_completion
        if last is None or last.action.type != action.type:
            return False
        if isinstance(action, InteractionAction) and isinstance(last.action, InteractionAction):
            return action.id == last.action.id
        # scrolling multiple times in a row is fine, going back multiple times in a row is suspicious
        return isinstance(action, GoBackAction)

    def _agent_state(self, obs: Observation, answer: ChoiceAnswer, action: BaseAction) -> AgentState:
        last_result, last_completion = self.trajectory.last_result, self.trajectory.last_completion
        status: Literal["success", "failure", "unknown"] = "unknown"
        if last_result is not None:
            status = "success" if last_result.success else "failure"
        labels = {a.id: a.text_label for a in obs.space.interaction_actions}
        target = f" '{labels.get(action.id) or action.id}'" if isinstance(action, InteractionAction) else ""
        return AgentState(
            previous_goal_status=status,
            previous_goal_eval=f"Previous action status: {status}",
            page_summary=f"{obs.metadata.title} ({obs.metadata.url})",
            relevant_interactions=[
                RelevantInteraction(id=option, reason=f"decision model probability: {prob:.2f}")
                for option, prob in answer.top(3)
                if option in labels and prob > 0
            ],
            # the decision model has no memory: carry over the one from the last LLM step
            memory=last_completion.state.memory if last_completion is not None else "No memory yet",
            next_goal=f"{action.name()}{target} (selected by decision model with confidence {answer.confidence:.2f})",
        )

    async def _fallback(self, request: AgentRunRequest, reason: str) -> AgentCompletion.InnerLlmCompletion:
        self.fallback_reasons[reason] += 1
        logger.info(f"🧠 Decision model fallback to LLM: {reason}")
        return await super().completion(request)

    @override
    async def completion(self, request: AgentRunRequest) -> AgentCompletion.InnerLlmCompletion:
        obs = self.trajectory.last_observation
        if obs is None or obs.space.is_empty():
            return await self._fallback(request, "empty action space")
        if len(obs.space.interaction_actions) + len(SPECIAL_OPTIONS) > MAX_CHOICE_OPTIONS:
            return await self._fallback(request, "too many actions")
        last_result = self.trajectory.last_result
        if last_result is not None and not last_result.success:
            # let the LLM reason about failures
            return await self._fallback(request, "previous action failed")

        state, questions = self._state(request, obs), self._questions(obs)
        if self.vault is not None:
            # hide vault leaked credentials within decision model inputs
            state = BaseVault.recursive_replace_mapping(state, self.vault.get_replacement_map())
        try:
            response = await self.decision.decide(state=state, questions=questions)
        except DecisionModelError as e:
            logger.warning(f"🎲 {e.dev_message}")
            return await self._fallback(request, "decision model error")

        answer = response.choice("next")
        logger.info(
            f"🎲 Decision model: {answer.top(3)} (confidence={answer.confidence:.2f}, done={response.noul('done'):.2f})"
        )
        if answer.confidence < self.confidence_threshold:
            return await self._fallback(request, "low confidence")
        if response.noul("done") >= 0.5:
            return await self._fallback(request, "task completion")
        action = self._select_action(obs, answer)
        if action is None:
            return await self._fallback(
                request, f"requires LLM: {answer.choice if answer.choice in SPECIAL_OPTIONS else 'parameters'}"
            )
        if self._is_repeated(action):
            return await self._fallback(request, "repeated action")

        self.nb_decision_steps += 1
        return AgentCompletion.InnerLlmCompletion(state=self._agent_state(obs, answer, action), action=action)

    @override
    async def _run(self, request: AgentRunRequest) -> AgentResponse:
        try:
            return await super()._run(request)
        finally:
            nb_fallbacks = sum(self.fallback_reasons.values())
            stats = f"{self.nb_decision_steps} direct steps, {nb_fallbacks} LLM fallbacks {dict(self.fallback_reasons)}"
            logger.info(f"🎲 Decision model stats: {stats}, cost=${self.decision.usage.cost:.5f}")
