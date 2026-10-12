import os

from pydantic import BaseModel

from notte_browser.llm.models import LlmModel


class LlmSettings(BaseModel):
    """Settings of the optional LLM extra, read from `NOTTE_LLM_*` environment variables."""

    # Model used for structured scraping when the call does not pick one.
    model: str
    nb_retries_structured_output: int = 2
    temperature: float = 0.0

    @staticmethod
    def from_env() -> "LlmSettings":
        return LlmSettings(
            model=os.getenv("NOTTE_LLM_MODEL") or LlmModel.default().value,
            nb_retries_structured_output=int(os.getenv("NOTTE_LLM_NB_RETRIES_STRUCTURED_OUTPUT", "2")),
            temperature=float(os.getenv("NOTTE_LLM_TEMPERATURE", "0.0")),
        )
