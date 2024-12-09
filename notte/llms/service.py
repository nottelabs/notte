from pathlib import Path
from typing import Any, ClassVar, final

from litellm import ModelResponse
from notte.llms.engine import LLMEngine
from notte.llms.prompt import PromptLibrary
import os
PROMPT_DIR = Path(__file__).parent.parent / "llms" / "prompts"


class ModelRouter:
    NOTTE_BASE_MODEL: ClassVar[str] = "NOTTE_BASE_MODEL"

    def get(self) -> str:
        model = os.getenv(self.NOTTE_BASE_MODEL)
        if model is None:
            return "groq/llama-3.3-70b-versatile"
        return model
    
    @staticmethod
    def set(model: str):
        os.environ[ModelRouter.NOTTE_BASE_MODEL] = model


@final
class LLMService:

    def __init__(self):
        self.llm = LLMEngine()
        self.lib = PromptLibrary(str(PROMPT_DIR))
        self.router = ModelRouter()

    def completion(
        self,
        prompt_id: str,
        variables: dict[str, Any] | None = None,
    ) -> ModelResponse:
        model = self.router.get()
        messages = self.lib.materialize(prompt_id, variables)
        return self.llm.completion(messages=messages, model=model)
