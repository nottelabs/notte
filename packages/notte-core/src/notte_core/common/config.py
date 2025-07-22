import os
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self, Unpack

import toml
from pydantic import BaseModel, computed_field
from typing_extensions import TypedDict, override

from notte_core import set_logger_mode
from notte_core.errors.base import ErrorMode

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.toml"

if not DEFAULT_CONFIG_PATH.exists():
    raise FileNotFoundError(f"Config file not found: {DEFAULT_CONFIG_PATH}")

ScreenshotType = Literal["raw", "full", "last_action"]


class PlaywrightProxySettings(TypedDict, total=False):
    server: str
    bypass: str | None
    username: str | None
    password: str | None


class LlmProvider(StrEnum):
    openai = "openai"
    gemini = "gemini"
    vertex_ai = "vertex_ai"
    openrouter = "openrouter"
    cerebras = "cerebras"
    groq = "groq"
    perplexity = "perplexity"
    deepseek = "deepseek"
    ollama = "ollama"

    @property
    def context_length(self) -> int:
        match self:
            case LlmProvider.cerebras:
                return 16_000
            case LlmProvider.groq:
                return 8_000
            case LlmProvider.perplexity:
                return 64_000
            case _:
                return 128_000

    @property
    def apikey_name(self) -> str:
        match self:
            case LlmProvider.gemini:
                return "GEMINI_API_KEY"
            case LlmProvider.vertex_ai:
                return "GOOGLE_APPLICATION_CREDENTIALS"
            case LlmProvider.openai:
                return "OPENAI_API_KEY"
            case LlmProvider.groq:
                return "GROQ_API_KEY"
            case LlmProvider.perplexity:
                return "PERPLEXITY_API_KEY"
            case LlmProvider.cerebras:
                return "CEREBRAS_API_KEY"
            case LlmProvider.openrouter:
                return "OPENROUTER_API_KEY"
            case LlmProvider.deepseek:
                return "DEEPSEEK_API_KEY"
            case LlmProvider.ollama:
                return "OLLAMA_API_KEY"
            case _:  # pyright: ignore[reportUnnecessaryComparison]
                raise ValueError(f"No API key name found for provider: {self}")  # pyright: ignore[reportUnreachable]

    def has_apikey_in_env(self) -> bool:
        if self == LlmProvider.ollama:
            return True
        return os.getenv(self.apikey_name) is not None


class LlmModel(StrEnum):
    openai = "openai/gpt-4o"
    gemini = "gemini/gemini-2.0-flash"
    gemini_vertex = "vertex_ai/gemini-2.0-flash"
    gemma = "openrouter/google/gemma-3-27b-it"
    cerebras = "cerebras/llama-3.3-70b"
    groq = "groq/llama-3.3-70b-versatile"
    perplexity = "perplexity/sonar-pro"
    deepseek = "deepseek/deepseek-r1"

    @property
    def provider(self) -> LlmProvider:
        return self.get_provider(self.value)

    @staticmethod
    def get_provider(model: str) -> LlmProvider:
        provider_str = model.split("/")[0]
        if provider_str not in list(LlmProvider):
            raise ValueError(f"Invalid provider: {provider_str}")
        return LlmProvider(provider_str)

    @property
    def context_length(self) -> int:
        return self.provider.context_length

    @staticmethod
    def default() -> "LlmModel":
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            return LlmModel.gemini_vertex
        return LlmModel.gemini

    @staticmethod
    def valid() -> set[str]:
        return {model.value for model in LlmModel if model.provider.has_apikey_in_env()}


class BrowserType(StrEnum):
    CHROMIUM = "chromium"
    CHROME = "chrome"
    FIREFOX = "firefox"


class ScrapingType(StrEnum):
    MARKDOWNIFY = "markdownify"
    MAIN_CONTENT = "main_content"


class PerceptionType(StrEnum):
    FAST = "fast"
    DEEP = "deep"


class RaiseCondition(StrEnum):
    """How to raise an error when the agent fails to complete a step.

    Either immediately upon failure, after retry, or never.
    """

    IMMEDIATELY = "immediately"
    RETRY = "retry"
    NEVER = "never"


class NotteConfigDict(TypedDict, total=False):
    # [log]
    level: str
    verbose: bool
    logging_mode: ErrorMode

    # [llm]
    reasoning_model: str
    max_history_tokens: int | None
    nb_retries_structured_output: int
    nb_retries: int
    clip_tokens: int
    use_llamux: bool
    temperature: float

    # [browser]
    headless: bool
    user_agent: str | None
    solve_captchas: bool
    viewport_width: int | None
    viewport_height: int | None
    screenshot_type: ScreenshotType
    cdp_url: str | None
    browser_type: BrowserType
    web_security: bool
    custom_devtools_frontend: str | None
    debug_port: int | None
    chrome_args: list[str] | None

    # [perception]
    perception_type: PerceptionType
    perception_model: str | None

    # [scraping]
    scraping_type: ScrapingType

    # [error]
    max_error_length: int
    raise_condition: RaiseCondition
    max_consecutive_failures: int

    # [proxy]
    proxy_host: str | None
    proxy_username: str | None
    proxy_password: str | None
    proxy_bypass: str | None

    # [agent]
    max_steps: int
    use_vision: bool

    # [dom_parsing]
    highlight_elements: bool
    focus_element: int
    viewport_expansion: int

    # [playwright wait/timeout]
    timeout_goto_ms: int
    timeout_default_ms: int
    timeout_action_ms: int
    wait_retry_snapshot_ms: int
    wait_short_ms: int
    empty_page_max_retry: int

    # [misc]
    enable_profiling: bool


class TomlConfig(BaseModel):
    @classmethod
    def from_toml(cls, **data: Unpack[NotteConfigDict]) -> Self:
        """Load settings from a TOML file."""

        # load default config
        with DEFAULT_CONFIG_PATH.open("r") as f:
            toml_data = toml.load(f)

        path = os.getenv("NOTTE_CONFIG_PATH")

        if path is not None:
            path = Path(path)
            if not path.exists():
                raise FileNotFoundError(f"Config file not found: {path}")

            # load external config
            with path.open("r") as f:
                external_toml_data = toml.load(f)

            # merge configs
            toml_data = {**toml_data, **external_toml_data}
        toml_data = {**toml_data, **data}

        return cls.model_validate(toml_data)


class NotteConfig(TomlConfig):
    class Config:
        # frozen config
        frozen: bool = True
        extra: str = "forbid"

    # [log]
    level: str
    verbose: bool
    logging_mode: ErrorMode

    # [llm]
    reasoning_model: str = LlmModel.default().value
    max_history_tokens: int | None = None
    nb_retries_structured_output: int
    nb_retries: int
    clip_tokens: int
    use_llamux: bool
    temperature: float

    # [browser]
    headless: bool
    solve_captchas: bool
    user_agent: str | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    cdp_url: str | None = None
    screenshot_type: ScreenshotType = "last_action"
    browser_type: BrowserType
    web_security: bool
    custom_devtools_frontend: str | None = None
    debug_port: int | None = None
    chrome_args: list[str] | None = None

    # [perception]
    perception_type: PerceptionType = PerceptionType.DEEP
    perception_model: str | None = None  # if none use reasoning_model

    # [scraping]
    scraping_type: ScrapingType

    # [error]
    max_error_length: int
    raise_condition: RaiseCondition
    max_consecutive_failures: int

    # [proxy]
    proxy_host: str | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None
    proxy_bypass: str | None = None

    # [agent]
    max_steps: int
    use_vision: bool

    # [dom_parsing]
    highlight_elements: bool
    focus_element: int
    viewport_expansion: int

    # [playwright wait/timeout]
    timeout_goto_ms: int
    timeout_default_ms: int
    timeout_action_ms: int
    wait_retry_snapshot_ms: int
    wait_short_ms: int
    empty_page_max_retry: int

    # [misc]
    enable_profiling: bool

    @override
    def model_post_init(self, context: Any, /) -> None:
        set_logger_mode(self.logging_mode)

    @computed_field
    @property
    def playwright_proxy(self) -> PlaywrightProxySettings | None:
        if self.proxy_host is None:
            return None

        return PlaywrightProxySettings(
            server=self.proxy_host,
            bypass=self.proxy_bypass,
            username=self.proxy_username,
            password=self.proxy_password,
        )


# DESIGN CHOICES after discussion with the leo
# 1. flat config structure with comments like # [browser] to structure the file
# 2. Root config structure should be global for all packages (notte-core, notte-agent, notte-browser) and should therefore be put in notte-core
# 3. Users that want extra config options can create their own config file and pass it to the from_toml method. The rule is that the new params override the defaul one
#### -> This is very good because we can enforce headless=True on the CICD and docker images with this without breaking the config for the users
# 4. If some agents required a parameter to be set to a certain value, we can add a model_validator to the config class that will check that the parameter is set to the correct value.
# 5. For computed fields such as `max_history_token` if the user does not set it, we use our computed value otherwise we default to the user value.


config = NotteConfig.from_toml()
