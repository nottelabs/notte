import os
from pathlib import Path
from typing import Any

import litellm
from llamux import Router
from loguru import logger

from notte.llms.prompt import PromptLibrary

PROMPT_DIR = Path(__file__).parent.parent / "llms" / "prompts"
LLAMUX_CONFIG = Path(__file__).parent.parent / "llms" / "config" / "endpoints.csv"

if "LLAMUX_CONFIG_PATH" in os.environ:
    logger.info(f"Using custom LLAMUX config path: {os.environ['LLAMUX_CONFIG_PATH']}")
llamux_config = os.getenv("LLAMUX_CONFIG_PATH", str(LLAMUX_CONFIG))


class LLMService:

    def __init__(self) -> None:
        self.lib: PromptLibrary = PromptLibrary(str(PROMPT_DIR))
        path = Path(llamux_config)
        if not path.exists():
            raise FileNotFoundError(f"LLAMUX config file not found at {path}")
        self.router: Router = Router.from_csv(llamux_config)

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
