from pathlib import Path
from typing import Any, final

from litellm import ModelResponse
from llamux import Router

from notte.llms.prompt import PromptLibrary

PROMPT_DIR = Path(__file__).parent.parent / "llms" / "prompts"
ENDPOINT_DIR = Path(__file__).parent.parent / "llms" / "config" / "endpoints.csv"


@final
class LLMService:

    def __init__(self):
        self.lib = PromptLibrary(str(PROMPT_DIR))
        self.router = Router.from_csv(str(ENDPOINT_DIR))

    def completion(
        self,
        prompt_id: str,
        variables: dict[str, Any] | None = None,
    ) -> ModelResponse:
        messages = self.lib.materialize(prompt_id, variables)
        return self.router.completion(messages=messages)
