import json
from typing import Any

from notte_core.actions import CompletionAction
from notte_core.browser.observation import ExecutionResult, TimedSpan, TrajectoryProgress
from notte_core.common.logging import logger
from notte_core.trajectory import Trajectory
from notte_llm.decision import DecisionEngine, DecisionModelError, DecisionQuestion, NoulQuestion
from pydantic import BaseModel

from notte_agent.common.perception import BasePerception
from notte_agent.common.validator import CompletionValidator

VALIDATION_INSTRUCTIONS = (
    "`agent_answer` is a correct and complete answer to `task`, "
    "and it is fully supported by the content of `page` or `previous_actions`"
)
MAX_VALIDATION_INPUT_CHARS = 60_000


class DecisionValidator:
    """
    Validates the agent output using a decision model: the LLM validator is only used when the decision model
    is not confident that the answer is valid (the LLM is then able to explain to the agent what is wrong).
    """

    def __init__(
        self,
        decision: DecisionEngine,
        llm_validator: CompletionValidator,
        perception: BasePerception,
        confidence_threshold: float = 0.75,
        max_actions: int = 3,
    ):
        self.decision: DecisionEngine = decision
        self.llm_validator: CompletionValidator = llm_validator
        self.perception: BasePerception = perception
        self.confidence_threshold: float = confidence_threshold
        self.max_actions: int = max_actions
        self.nb_decision_validations: int = 0

    async def validate(
        self,
        task: str,
        output: CompletionAction,
        history: Trajectory,
        progress: TrajectoryProgress,
        response_format: type[BaseModel] | None = None,
    ) -> ExecutionResult:
        async def llm_validation() -> ExecutionResult:
            return await self.llm_validator.validate(
                task=task, output=output, history=history, progress=progress, response_format=response_format
            )

        last_obs = history.last_observation
        if last_obs is None or not output.success:
            return await llm_validation()
        if response_format is not None:
            if not CompletionValidator.validate_response_format(output, response_format).is_valid:
                # no LLM call is performed in this case
                return await llm_validation()

        with TimedSpan.capture() as span:
            results = list(history.execution_results())[-self.max_actions :]
            state: dict[str, Any] = {
                "task": task,
                "agent_answer": output.answer,
                "previous_actions": [self.perception.perceive_action_result(result) for result in results],
                "current_url": last_obs.metadata.url,
            }
            state["page"] = last_obs.space.description[: max(0, MAX_VALIDATION_INPUT_CHARS - len(json.dumps(state)))]
            questions: dict[str, DecisionQuestion] = {"valid": NoulQuestion(instructions=VALIDATION_INSTRUCTIONS)}
            try:
                valid = (await self.decision.decide(state=state, questions=questions)).noul("valid")
            except DecisionModelError as e:
                logger.warning(f"🎲 {e.dev_message}")
                return await llm_validation()
        logger.info(f"🎲 Decision model validation: {valid:.2f}")
        if valid < self.confidence_threshold:
            return await llm_validation()

        self.nb_decision_validations += 1
        return ExecutionResult(
            action=output,
            success=True,
            message=f"The decision model validated the answer of the agent (probability={valid:.2f})",
            started_at=span.started_at,
            ended_at=span.close().ended_at,
        )
