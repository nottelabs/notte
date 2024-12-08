from pathlib import Path
from typing import Any, final

from litellm import ModelResponse
from notte.llms.engine import LLMEngine
from notte.llms.prompt import PromptLibrary

PROMPT_DIR = Path(__file__).parent.parent / "llms" / "prompts"


class ModelRouter:
    def __init__(self):
        pass

    def get(self) -> str:
        # return "groq/llama-3.1-70b-versatile"
        return "anthropic/claude-3-5-sonnet-20240620"


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
