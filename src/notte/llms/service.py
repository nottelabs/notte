import os
from pathlib import Path
from typing import Any, ClassVar

import tiktoken
from litellm import ModelResponse  # type: ignore[import]
from llamux import Router  # type: ignore[import]
from loguru import logger

from notte.errors.llm import InvalidPromptTemplateError
from notte.llms.engine import LLMEngine, TResponseFormat
from notte.llms.prompt import PromptLibrary

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

    DEFAULT_MODEL: ClassVar[str] = "groq/llama-3.3-70b-versatile"

    def __init__(
        self, base_model: str | None = None, verbose: bool = False, structured_output_retries: int = 0
    ) -> None:
        self.lib: PromptLibrary = PromptLibrary(str(PROMPT_DIR))
        llamux_config = get_llamux_config(verbose)
        path = Path(llamux_config)
        if not path.exists():
            raise FileNotFoundError(f"LLAMUX config file not found at {path}")
        self.router: Router = Router.from_csv(llamux_config)
        self.base_model: str | None = base_model or self.DEFAULT_MODEL
        self.tokenizer: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")
        self.verbose: bool = verbose
        self.structured_output_retries: int = structured_output_retries

    def get_base_model(self, messages: list[dict[str, Any]]) -> tuple[str, str | None]:
        eid: str | None = None
        router = "fixed"
        if self.base_model is None:
            router = "llamux"
            provider, model, eid, _ = self.router.query(messages=messages)
            base_model = f"{provider}/{model}"
        else:
            base_model = self.base_model
        token_len = self.estimate_tokens(text="\n".join([m["content"] for m in messages]))
        if self.verbose:
            logger.debug(f"llm router '{router}' selected '{base_model}' for approx {token_len} tokens")
        return base_model, eid

    def clip_tokens(self, document: str, max_tokens: int) -> str:
        tokens = self.tokenizer.encode(document)
        if len(tokens) > max_tokens:
            logger.info(f"Cannot process document, exceeds max tokens: {len(tokens)} > {max_tokens}. Clipping...")
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
        if eid is not None:
            # log usage to LLAMUX router if eid is provided
            tokens: int = response.usage.total_tokens  # type: ignore[attr-defined]
            self.router.log(tokens=tokens, endpoint_id=eid)  # type: ignore[arg-type]
        return response
