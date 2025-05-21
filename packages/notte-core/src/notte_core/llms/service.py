import os
from pathlib import Path
from typing import Any

import tiktoken
from litellm import ModelResponse  # type: ignore[import]
from llamux import Router  # type: ignore[import]
from loguru import logger

from notte_core.common.config import config
from notte_core.errors.llm import InvalidPromptTemplateError
from notte_core.llms.engine import LLMEngine, LlmModel, TResponseFormat
from notte_core.llms.prompt import PromptLibrary

PROMPT_DIR = Path(__file__).parent.parent / "llms" / "prompts"
LLAMUX_CONFIG = Path(__file__).parent.parent / "llms" / "config" / "endpoints.csv"


def get_llamux_config(verbose: bool = False) -> str:
    if "LLAMUX_CONFIG_PATH" in os.environ:
        if verbose:
            logger.info(f"Using custom LLAMUX config path: {os.environ['LLAMUX_CONFIG_PATH']}")
    else:
        if verbose:
            logger.info(f"Using default LLAMUX config path: {LLAMUX_CONFIG}")
    return os.getenv("LLAMUX_CONFIG_PATH", str(LLAMUX_CONFIG))


class LLMService:
    """
    LLM service for Notte.
    """

    def __init__(self, base_model: str | None = None) -> None:
        self.lib: PromptLibrary = PromptLibrary(str(PROMPT_DIR))
        self.router: Router | None = None

        if config.use_llamux:
            llamux_config = get_llamux_config(config.verbose)
            path = Path(llamux_config)
            if not path.exists():
                raise FileNotFoundError(f"LLAMUX config file not found at {path}")
            self.router = Router.from_csv(llamux_config)
        self.base_model: str = base_model or LlmModel.default()
        self.tokenizer: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")
        self.verbose: bool = config.verbose
        self.structured_output_retries: int = config.nb_retries_structured_output

    def context_length(self) -> int:
        return LlmModel.context_length(self.base_model)

    def get_base_model(self, messages: list[dict[str, Any]]) -> tuple[str, str | None]:
        eid: str | None = None

        if self.router is not None:
            router = "llamux"
            provider, model, eid, _ = self.router.query(messages=messages)
            base_model = f"{provider}/{model}"
        else:
            router = "fixed"
            base_model = self.base_model

        token_len = self.estimate_tokens(text="\n".join([m["content"] for m in messages]))
        if self.verbose:
            logger.debug(f"llm router '{router}' selected '{base_model}' for approx {token_len} tokens")
        return base_model, eid

    def clip_tokens(self, document: str, max_tokens: int | None = None) -> str:
        max_tokens = max_tokens or (self.context_length() - 2000)
        tokens = self.tokenizer.encode(document)
        if len(tokens) > max_tokens:
            logger.warning(f"Cannot process document, exceeds max tokens: {len(tokens)} > {max_tokens}. Clipping...")
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

    def structured_completion(
        self,
        prompt_id: str,
        response_format: type[TResponseFormat],
        variables: dict[str, Any] | None = None,
    ) -> TResponseFormat:
        messages = self.lib.materialize(prompt_id, variables)
        base_model, _ = self.get_base_model(messages)
        return LLMEngine(
            structured_output_retries=self.structured_output_retries, verbose=self.verbose
        ).structured_completion(
            messages=messages,  # type: ignore[arg-type]
            response_format=response_format,
            model=base_model,
        )

    def completion(
        self,
        prompt_id: str,
        variables: dict[str, Any] | None = None,
    ) -> ModelResponse:
        messages = self.lib.materialize(prompt_id, variables)
        base_model, eid = self.get_base_model(messages)
        response = LLMEngine(verbose=self.verbose).completion(
            messages=messages,  # type: ignore[arg-type]
            model=base_model,
        )
        if eid is not None and self.router is not None:
            # log usage to LLAMUX router if eid is provided
            tokens: int = response.usage.total_tokens  # type: ignore[attr-defined]
            self.router.log(tokens=tokens, endpoint_id=eid)  # type: ignore[arg-type]
        return response
