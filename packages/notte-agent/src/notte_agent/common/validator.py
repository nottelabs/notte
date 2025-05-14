from typing import final

import chevron
from notte_browser.session import TrajectoryStep
from notte_core.actions.base import CompletionAction
from notte_core.llms.engine import LLMEngine
from pydantic import BaseModel

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

Your turn:
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
    ):
        self.use_vision = use_vision
        self.include_attributes = include_attributes
        self.llm: LLMEngine = llm
        self.conv: Conversation = Conversation()
        self.perception: BasePerception = perception

    @staticmethod
    def example() -> CompletionValidation:
        return CompletionValidation(
            is_valid=False,
            reason="The user wanted to search for 'cat photos', but the agent searched for 'dog photos' instead.",
        )

    def validation_message(
        self,
        output: CompletionAction,
        step: TrajectoryStep,
    ) -> str:
        return f"""
Last observation:
{self.perception.perceive(step.obs)}

Last action:
{step.action.model_dump_json(exclude_unset=True)}

Agent task output:
{output}
"""

    def validate(
        self,
        task: str,
        output: CompletionAction,
        step: TrajectoryStep,
    ) -> CompletionValidation:
        """Validate the output of the last action is what the user wanted"""
        self.conv.reset()
        system_prompt = chevron.render(system_rules, {"task": task, "example": self.example().model_dump_json()})
        self.conv.add_system_message(content=system_prompt)
        self.conv.add_user_message(
            content=self.validation_message(output, step),
            image=(step.obs.screenshot if self.use_vision else None),
        )

        answer: CompletionValidation = self.llm.structured_completion(self.conv.messages(), CompletionValidation)
        return answer
