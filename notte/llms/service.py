import os
from pathlib import Path
from typing import Any

import litellm
import tiktoken
from llamux import Router
from loguru import logger

from notte.errors.llm import InvalidPromptTemplateError
from notte.llms.prompt import PromptLibrary

PROMPT_DIR = Path(__file__).parent.parent / "llms" / "prompts"
LLAMUX_CONFIG = Path(__file__).parent.parent / "llms" / "config" / "endpoints.csv"

if "LLAMUX_CONFIG_PATH" in os.environ:
    logger.info(f"Using custom LLAMUX config path: {os.environ['LLAMUX_CONFIG_PATH']}")
else:
    logger.info(f"Using default LLAMUX config path: {LLAMUX_CONFIG}")
llamux_config = os.getenv("LLAMUX_CONFIG_PATH", str(LLAMUX_CONFIG))


class LLMService:

    def __init__(self) -> None:
        self.lib: PromptLibrary = PromptLibrary(str(PROMPT_DIR))
        path = Path(llamux_config)
        if not path.exists():
            raise FileNotFoundError(f"LLAMUX config file not found at {path}")
        self.router: Router = Router.from_csv(llamux_config)
        self.tokenizer: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")

    def estimate_tokens(
        self, text: str | None = None, prompt_id: str | None = None, variables: dict[str, Any] | None = None
    ) -> int:
        if text is None:
            if prompt_id is None or variables is None:
                raise InvalidPromptTemplateError(
                    prompt_id=prompt_id or "unknown",
                    message="for token estimation, prompt_id and variables must be provided if text is not provided",
                )
            messages = self.lib.materialize(prompt_id, variables)
            text = "\n".join([m["content"] for m in messages])
        return len(self.tokenizer.encode(text))

    def completion(
        self,
        prompt_id: str,
        variables: dict[str, Any] | None = None,
    ) -> litellm.ModelResponse:
        messages = self.lib.materialize(prompt_id, variables)
        provider, model, eid, _ = self.router.query(messages=messages)
        token_len = self.estimate_tokens(prompt_id=prompt_id, variables=variables)
        logger.debug(f"using {provider}/{model} for approx {token_len} tokens")
        response = litellm.completion(
            model=f"{provider}/{model}",
            messages=messages,
        )
        self.router.log(response.usage.total_tokens, eid)
        return response
