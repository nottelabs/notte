import os
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self, TypedDict

import toml
from loguru import logger
from pydantic import BaseModel
from typing_extensions import override

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.toml"

if not DEFAULT_CONFIG_PATH.exists():
    raise FileNotFoundError(f"Config file not found: {DEFAULT_CONFIG_PATH}")


class FrozenConfig(BaseModel):
    verbose: bool = False

    class Config:
        frozen: bool = True
        extra: str = "forbid"

    def _copy_and_validate(self: Self, **kwargs: Any) -> Self:
        # kwargs should be validated before being passed to model_copy
        _ = self.model_validate(kwargs)
        config = self.model_copy(deep=True, update=kwargs)
        return config

    def set_verbose(self: Self) -> Self:
        return self._copy_and_validate(verbose=True)

    def set_deep_verbose(self: Self, value: bool = True) -> Self:
        updated_fields: dict[str, Any] = {
            field: config.set_deep_verbose(value=value)
            for field, config in self.__dict__.items()
            if isinstance(config, FrozenConfig)
        }
        if "session" in updated_fields:
            updated_fields["force_session"] = True
        return self._copy_and_validate(**updated_fields, verbose=value)


class ParameterDict(TypedDict):
    pass


class TomlConfig(BaseModel):
    @classmethod
    def from_toml(cls, data: ParameterDict | None = None) -> Self:
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
            toml_data = {**toml_data, **external_toml_data, **(data or {})}

        return cls.model_validate(toml_data)


class BrowserType(StrEnum):
    CHROMIUM = "chromium"
    CHROME = "chrome"
    FIREFOX = "firefox"


class ScrapingType(StrEnum):
    MARKDOWNIFY = "markdownify"
    MAIN_CONTENT = "main_content"
    LLM_EXTRACT = "llm_extract"


class RaiseCondition(StrEnum):
    """How to raise an error when the agent fails to complete a step.

    Either immediately upon failure, after retry, or never.
    """

    IMMEDIATELY = "immediately"
    RETRY = "retry"
    NEVER = "never"


class NotteConfig(TomlConfig):
    class Config:
        # frozen config
        frozen: bool = True
        extra: str = "forbid"

    # [log]
    level: str
    verbose: bool
    logging_mode: Literal["user", "dev", "agent"]

    # [llm]
    reasoning_model: str
    max_history_tokens: int | None = None
    nb_retries_structured_output: int
    nb_retries: int
    clip_tokens: int
    use_llamux: bool

    # [browser]
    headless: bool
    user_agent: str | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    cdp_url: str | None = None
    browser_type: BrowserType
    web_security: bool
    custom_devtools_frontend: str | None = None
    debug_port: int | None = None
    chrome_args: list[str] | None = None

    # [perception]
    enable_perception: bool
    perception_model: str | None = None  # if none use reasoning_model

    # [scraping]
    auto_scrape: bool
    use_llm: bool
    scraping_type: ScrapingType

    # [error]
    max_error_length: int
    raise_condition: RaiseCondition
    max_consecutive_failures: int

    # [proxy]
    proxy_host: str | None = None
    proxy_port: int | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None

    # [agent]
    max_steps: int
    max_actions_per_step: int
    human_in_the_loop: bool
    use_vision: bool

    @override
    def model_post_init(self, context: Any, /) -> None:
        match self.logging_mode:
            case "dev":
                format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
                logger.configure(handlers=[dict(sink=sys.stderr, level="DEBUG", format=format)])  # type: ignore
                # self.set_deep_verbose(True)
            case "user":
                pass
                # verbose=True,
                # window=self.window.set_verbose(),
                # action=self.action.set_verbose(),
            case "agent":
                format = "<level>{level: <8}</level> - <level>{message}</level>"
                logger.configure(handlers=[dict(sink=sys.stderr, level="INFO", format=format)])  # type: ignore
                # self.set_deep_verbose(False)


# DESIGN CHOICES after discussion with the leo
# 1. flat config structure with comments like # [browser] to structure the file
# 2. Root config structure should be global for all packages (notte-core, notte-agent, notte-browser) and should therefore be put in notte-core
# 3. Users that want extra config options can create their own config file and pass it to the from_toml method. The rule is that the new params override the defaul one
#### -> This is very good because we can enforce headless=True on the CICD and docker images with this without breaking the config for the users
# 4. If some agents required a parameter to be set to a certain value, we can add a model_validator to the config class that will check that the parameter is set to the correct value.
# 5. For computed fields such as `max_history_token` if the user does not set it, we use our computed value otherwise we default to the user value.


config = NotteConfig.from_toml()
