from pathlib import Path
from typing import Any

from notte_core.config import config
from notte_core.logging import logger
from notte_core.schema import TResponseFormat

from notte_llm.config import LlmSettings
from notte_llm.engine import LLMEngine
from notte_llm.prompt import PromptLibrary

PROMPT_DIR = Path(__file__).parent / "prompts"


class LLMService:
    """
    LLM service used for structured data extraction (`scrape(instructions=..., response_format=...)`).
    """

    def __init__(self, base_model: str | None = None) -> None:
        self.lib: PromptLibrary = PromptLibrary(str(PROMPT_DIR))
        settings = LlmSettings.from_env(model=base_model)
        self.base_model: str = base_model or settings.model
        self.context_tokens: int = settings.context_tokens
        self.verbose: bool = config.verbose
        self.nb_retries_structured_output: int = settings.nb_retries_structured_output

    def context_length(self) -> int:
        return self.context_tokens

    def clip_tokens(self, document: str, max_tokens: int | None = None) -> str:
        # Approximate four characters per token and reserve room for prompts/output.
        max_tokens = max(0, self.context_length() - 2000) if max_tokens is None else max_tokens
        if max_tokens < 0:
            raise ValueError("max_tokens must be non-negative")
        max_chars = max_tokens * 4
        if len(document) > max_chars:
            logger.debug(f"Clipping document to approximately {max_tokens} tokens ({max_chars} characters)")
        return document[:max_chars]

    async def structured_completion(
        self,
        prompt_id: str,
        response_format: type[TResponseFormat],
        variables: dict[str, Any] | None = None,
        use_strict_response_format: bool = True,
        extra_body: dict[str, Any] | None = None,
    ) -> TResponseFormat:
        messages = self.lib.materialize(prompt_id, variables)
        return await LLMEngine(
            model=self.base_model,
            nb_retries_structured_output=self.nb_retries_structured_output,
            verbose=self.verbose,
            extra_body=extra_body,
        ).structured_completion(
            messages=messages,
            response_format=response_format,
            model=self.base_model,
            use_strict_response_format=use_strict_response_format,
        )
