from pathlib import Path
from typing import Any

import tiktoken
from litellm import ModelResponse  # type: ignore[import]
from notte_core.common.config import config
from notte_core.common.logging import logger
from notte_core.common.types import TResponseFormat
from notte_core.errors.llm import InvalidPromptTemplateError

from notte_llm.config import LlmSettings
from notte_llm.engine import LLMEngine
from notte_llm.models import LlmModel
from notte_llm.prompt import PromptLibrary

PROMPT_DIR = Path(__file__).parent / "prompts"


class LLMService:
    """
    LLM service used for structured data extraction (`scrape(instructions=..., response_format=...)`).
    """

    def __init__(self, base_model: str | None = None) -> None:
        self.lib: PromptLibrary = PromptLibrary(str(PROMPT_DIR))
        settings = LlmSettings.from_env()
        self.base_model: str = base_model or settings.model
        self.tokenizer: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")
        self.verbose: bool = config.verbose
        self.nb_retries_structured_output: int = settings.nb_retries_structured_output

    def context_length(self) -> int:
        return LlmModel.get_provider(self.base_model).context_length

    def clip_tokens(self, document: str, max_tokens: int | None = None) -> str:
        max_tokens = max_tokens or (self.context_length() - 2000)
        tokens = self.tokenizer.encode(document)
        if len(tokens) > max_tokens:
            logger.debug(f"Cannot process document, exceeds max tokens: {len(tokens)} > {max_tokens}. Clipping...")
            return self.tokenizer.decode(tokens[:max_tokens])
        return document

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

    async def structured_completion(
        self,
        prompt_id: str,
        response_format: type[TResponseFormat],
        variables: dict[str, Any] | None = None,
        use_strict_response_format: bool = True,
    ) -> TResponseFormat:
        messages = self.lib.materialize(prompt_id, variables)
        return await LLMEngine(
            nb_retries_structured_output=self.nb_retries_structured_output, verbose=self.verbose
        ).structured_completion(
            messages=messages,  # type: ignore[arg-type]
            response_format=response_format,
            model=self.base_model,
            use_strict_response_format=use_strict_response_format,
        )

    async def completion(
        self,
        prompt_id: str,
        variables: dict[str, Any] | None = None,
    ) -> ModelResponse:
        messages = self.lib.materialize(prompt_id, variables)
        return await LLMEngine(verbose=self.verbose).completion(
            messages=messages,  # type: ignore[arg-type]
            model=self.base_model,
        )
