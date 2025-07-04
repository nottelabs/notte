from typing import final

import chevron
from loguru import logger
from notte_core.actions import CompletionAction
from notte_core.browser.observation import ExecutionResult, Observation, TrajectoryProgress
from notte_core.llms.engine import LLMEngine
from notte_core.trajectory import Trajectory
from pydantic import BaseModel, ValidationError

from notte_agent.common.conversation import Conversation
from notte_agent.common.perception import BasePerception

system_rules = """
You are a validator of an agent who interacts with a browser.
Validate if the output of last action is what the user wanted and if the task is completed.
If the task is unclear defined, you can let it pass.
But if something is missing or the image does not show what was requested dont let it pass.
Try to understand the page and help the model with suggestions like scroll, do x, ... to get the solution right.

Task to validate: {{task}}.

Return a JSON object with 2 keys: `is_valid` and `reason`:
- `is_valid` is a boolean that indicates if the output is correct.
- `reason` is a string that explains why it is valid or not.

Example:
```json
{{&example}}
```
"""


class CompletionValidation(BaseModel):
    is_valid: bool
    reason: str


@final
class CompletionValidator:
    def __init__(
        self,
        llm: LLMEngine,
        perception: BasePerception,
        use_vision: bool = True,
        include_attributes: bool = True,
        max_steps: int = 3,
    ):
        self.use_vision = use_vision
        self.include_attributes = include_attributes
        self.llm: LLMEngine = llm
        self.conv: Conversation = Conversation()
        self.perception: BasePerception = perception
        self.max_actions: int = max_steps

    @staticmethod
    def example() -> CompletionValidation:
        return CompletionValidation(
            is_valid=False,
            reason="The user wanted to search for 'cat photos', but the agent searched for 'dog photos' instead.",
        )

    def validation_message(
        self, output: CompletionAction, history: Trajectory, progress: TrajectoryProgress, last_obs: Observation
    ) -> str:
        previous_results = list(history.execution_results())[-self.max_actions :]
        last_actions = "\n".join(self.perception.perceive_action_result(result) for result in previous_results)
        return f"""
I will now provide you some contextual information to help you validate the output of the agent.

Last observation:
{self.perception.perceive(last_obs, progress)}

Last action executions:
{last_actions}

Agent task output to validate:
{output.model_dump_agent()}

Your turn:
"""

    @staticmethod
    def validate_response_format(output: CompletionAction, response_format: type[BaseModel]) -> CompletionValidation:
        """Check that json output fits json schema"""
        try:
            _ = response_format.model_validate_json(output.answer)
        except ValidationError as e:
            return CompletionValidation(
                is_valid=False,
                reason=f"Expecting agent answer to follow the schema {response_format.model_json_schema()}, but found errors: {e.errors()}",
            )
        return CompletionValidation(
            is_valid=True, reason="The output returned by the agent is a valid according to the response format."
        )

    async def validate(
        self,
        task: str,
        output: CompletionAction,
        history: Trajectory,
        progress: TrajectoryProgress,
        response_format: type[BaseModel] | None = None,
    ) -> ExecutionResult:
        """Validate the output of the last action is what the user wanted"""

        # first, validate the output if provided a schema
        if response_format is not None:
            validation = CompletionValidator.validate_response_format(output, response_format)
            if not validation.is_valid:
                return ExecutionResult(action=output, success=False, message=validation.reason)

        observations = list(history.observations())
        if len(observations) == 0:
            return ExecutionResult(action=output, success=False, message="No observations")

        # then, validate that the answer is correct
        last_obs = observations[-1]

        self.conv.reset()
        system_prompt = chevron.render(system_rules, {"task": task, "example": self.example().model_dump_json()})
        self.conv.add_system_message(content=system_prompt)

        validation_message = self.validation_message(output, history, progress, last_obs)

        self.conv.add_user_message(
            content=validation_message,
            image=(last_obs.screenshot.bytes() if self.use_vision else None),
        )
        import json

        logger.warning(f"🔍 Validation messages:\n{json.dumps(self.conv.messages())}")
        answer: CompletionValidation = await self.llm.structured_completion(self.conv.messages(), CompletionValidation)
        return ExecutionResult(
            action=output,
            success=answer.is_valid,
            message=answer.reason,
        )
