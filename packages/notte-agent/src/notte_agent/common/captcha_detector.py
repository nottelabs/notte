from typing import final

import chevron
from notte_browser.session import TrajectoryStep
from notte_core.llms.engine import LLMEngine
from pydantic import BaseModel

from notte_agent.common.conversation import Conversation
from notte_agent.common.perception import BasePerception

system_rules = """
You are a captcha detector for web pages.
Analyze the provided screenshot and determine if there is a captcha present on the page.
A captcha can be in various forms such as:
- Image-based challenges
- Text-based challenges
- Checkbox-based verification
- Audio-based challenges
- Math problems
- Slider puzzles
- Blocked by network security
- etc.

Return a JSON object with 3 keys: `has_captcha`, `captcha_type`, and `description`:
- `has_captcha` is a boolean indicating if a captcha is present
- `captcha_type` is a string describing the type of captcha (or "none" if no captcha)
- `description` is a string providing details about the captcha's appearance and location

Example:
```json
{{&example}}
```

Your turn:
"""


class CaptchaDetection(BaseModel):
    has_captcha: bool
    captcha_type: str
    description: str


@final
class CaptchaDetector:
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
    def example() -> CaptchaDetection:
        return CaptchaDetection(
            has_captcha=True,
            captcha_type="image-based",
            description="A grid of 9 images is shown with the instruction 'Select all images containing traffic lights'",
        )

    def detection_message(self, step: TrajectoryStep) -> str:
        return f"""
Current page screenshot:
{self.perception.perceive(step.obs)}

Current page state:
{step.action.model_dump_json(exclude_unset=True)}
"""

    async def detect(
        self,
        step: TrajectoryStep,
    ) -> CaptchaDetection:
        """Detect if there is a captcha present in the current page screenshot"""
        self.conv.reset()
        system_prompt = chevron.render(system_rules, {"example": self.example().model_dump_json()})
        self.conv.add_system_message(content=system_prompt)
        self.conv.add_user_message(content=self.detection_message(step))

        answer: CaptchaDetection = await self.llm.structured_completion(self.conv.messages(), CaptchaDetection)
        return answer
