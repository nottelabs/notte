from pathlib import Path
from typing import Any, final

import litellm
from llamux import Router
from loguru import logger

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
    ) -> litellm.ModelResponse:
        messages = self.lib.materialize(prompt_id, variables)
        provider, model, eid, _ = self.router.query(messages=messages)
        logger.debug(f"using {provider}/{model}")
        response = litellm.completion(
            model=f"{provider}/{model}",
            messages=messages,
        )
        self.router.log(response.usage.total_tokens, eid)
        return response
