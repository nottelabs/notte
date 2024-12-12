import os
from pathlib import Path
from typing import Any, ClassVar, final

from litellm import ModelResponse

from notte.config import NotteConfig
from notte.llms.engine import LLMEngine
from notte.llms.prompt import PromptLibrary

PROMPT_DIR = Path(__file__).parent.parent / "llms" / "prompts"


class ModelRouter:

    def get(self) -> str:
        config = NotteConfig.load()
        if config.base_model is None:
            raise ValueError("Base model is not set")
        return config.base_model


@final
class LLMService:

    def __init__(
        self,
        llm: LLMEngine | None = None,
        lib: PromptLibrary | None = None,
        router: ModelRouter | None = None,
    ):
        self.llm = llm or LLMEngine()
        self.lib = lib or PromptLibrary(str(PROMPT_DIR))
        self.router = router or ModelRouter()

    def completion(
        self,
        prompt_id: str,
        variables: dict[str, Any] | None = None,
    ) -> ModelResponse:
        model = self.router.get()
        messages = self.lib.materialize(prompt_id, variables)
        return self.llm.completion(messages=messages, model=model)
