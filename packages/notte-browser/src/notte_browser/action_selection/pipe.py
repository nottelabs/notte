import datetime as dt

from notte_core.browser.observation import Observation
from notte_core.browser.perception import ObservationPerception
from notte_core.llms.service import LLMService
from pydantic import BaseModel


class SelectedAction(BaseModel):
    action_id: str
    description: str
    value: str | None = None


class ActionSelectionResult(BaseModel):
    success: bool
    reason: str
    actions: list[SelectedAction]

    def first(self) -> SelectedAction | None:
        if not self.success:
            return None
        if len(self.actions) == 0:
            return None
        return self.actions[0]


class ActionSelectionPipe:
    """
    Action selection pipe that selects the most relevant actions to take on the current page
    """

    def __init__(self, llmserve: LLMService, perception: ObservationPerception | None = None) -> None:
        self.llmserve: LLMService = llmserve
        self.perception: ObservationPerception = perception or ObservationPerception()

    def success_example(self) -> ActionSelectionResult:
        return ActionSelectionResult(
            success=True,
            reason="The user requested to 'click on the login button'. I found a authentication button with the id B3.",
            actions=[
                SelectedAction(
                    action_id="B3",
                    description="Authenticate with google account",
                )
            ],
        )

    def failure_example(self) -> ActionSelectionResult:
        return ActionSelectionResult(
            success=False,
            reason="The user requested information about a cat but the document is about a dog",
            actions=[],
        )

    async def forward(self, obs: Observation, instructions: str) -> ActionSelectionResult:
        content = self.perception.perceive(obs)
        response = await self.llmserve.structured_completion(
            prompt_id="action-selection",
            variables={
                "content": content,
                "instructions": instructions,
                "success_example": self.success_example().model_dump_json(),
                "failure_example": self.failure_example().model_dump_json(),
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "schema": ActionSelectionResult.model_json_schema(),
            },
            response_format=ActionSelectionResult,
        )
        return response
