import os
from urllib.parse import urlsplit

from notte_core.errors import MissingAPIKeyForModel
from pydantic import BaseModel, Field, SecretStr

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.5-flash"


class LlmSettings(BaseModel):
    """One OpenAI-compatible endpoint, configured through `NOTTE_LLM_*`."""

    base_url: str = DEFAULT_BASE_URL
    api_key: SecretStr | None = None
    model: str = DEFAULT_MODEL
    nb_retries_structured_output: int = Field(default=2, ge=0)
    temperature: float = 0.0
    context_tokens: int = Field(default=128_000, gt=0)

    @property
    def is_openrouter(self) -> bool:
        return urlsplit(self.base_url).hostname == "openrouter.ai"

    def require_api_key(self) -> str:
        if self.api_key is None or not self.api_key.get_secret_value():
            variables = "NOTTE_LLM_API_KEY"
            if self.base_url == DEFAULT_BASE_URL:
                variables += " or OPENROUTER_API_KEY"
            raise MissingAPIKeyForModel(self.model, api_key_variables=variables)
        return self.api_key.get_secret_value()

    @staticmethod
    def from_env(model: str | None = None) -> "LlmSettings":
        base_url = (os.getenv("NOTTE_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        url = urlsplit(base_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.query or url.fragment:
            raise ValueError("NOTTE_LLM_BASE_URL must be an HTTP(S) base URL without credentials, query, or fragment")
        model = model or os.getenv("NOTTE_LLM_MODEL")
        if not model:
            if base_url != DEFAULT_BASE_URL:
                raise ValueError("Set NOTTE_LLM_MODEL (or pass model=) when using a custom NOTTE_LLM_BASE_URL")
            model = DEFAULT_MODEL
        key = os.getenv("NOTTE_LLM_API_KEY")
        if key is None and base_url == DEFAULT_BASE_URL:
            key = os.getenv("OPENROUTER_API_KEY")
        return LlmSettings(
            base_url=base_url,
            api_key=SecretStr(key) if key is not None else None,
            model=model,
            nb_retries_structured_output=int(os.getenv("NOTTE_LLM_NB_RETRIES_STRUCTURED_OUTPUT", "2")),
            temperature=float(os.getenv("NOTTE_LLM_TEMPERATURE", "0.0")),
            context_tokens=int(os.getenv("NOTTE_LLM_CONTEXT_TOKENS", "128000")),
        )
