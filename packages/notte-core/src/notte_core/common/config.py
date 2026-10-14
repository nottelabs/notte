import os
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Required, Self, Unpack

from pydantic import BaseModel, Field, computed_field
from typing_extensions import TypedDict, override

from notte_core import LoggingSetup
from notte_core.common.logging import logger
from notte_core.errors.base import ErrorMode

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.toml"

if not DEFAULT_CONFIG_PATH.exists():
    raise FileNotFoundError(f"Config file not found: {DEFAULT_CONFIG_PATH}")


class CookieDict(TypedDict, total=False):
    """
    Cookie dictionary as returned by the session.get_cookies() method.
    """

    name: Required[str]
    value: Required[str]
    domain: Required[str]
    path: Required[str]
    httpOnly: Required[bool]
    expirationDate: float | None
    hostOnly: bool | None
    sameSite: Literal["Lax", "None", "Strict"] | None
    secure: bool | None
    session: bool | None
    storeId: str | None
    expires: float | None
    partitionKey: str | None


class PlaywrightProxySettings(TypedDict, total=False):
    server: str
    bypass: str | None
    username: str | None
    password: str | None


BrowserType = Literal["chromium", "chrome", "firefox", "chrome-nightly", "chrome-turbo"]


class BrowserBackend(StrEnum):
    PLAYWRIGHT = "playwright"
    PATCHRIGHT = "patchright"


PerceptionType = Literal["fast", "deep"]


class RaiseCondition(StrEnum):
    """How to raise an error when the agent fails to complete a step.

    Either immediately upon failure, after retry, or never.
    """

    IMMEDIATELY = "immediately"
    RETRY = "retry"
    NEVER = "never"


class NotteConfigDict(TypedDict, total=False):
    # [log]
    verbose: bool
    logging_mode: ErrorMode

    # [browser]
    headless: bool
    user_agent: str | None
    viewport_width: int | None
    viewport_height: int | None
    cdp_url: str | None
    browser_type: BrowserType
    browser_backend: BrowserBackend
    web_security: bool
    custom_devtools_frontend: str | None
    debug_port: int | None
    chrome_args: list[str] | None
    raise_on_session_execution_failure: bool
    evaluate_js_max_result_bytes: int
    evaluate_js_max_result_values: int

    # [error]
    raise_condition: RaiseCondition

    # [proxy]
    proxy_host: str | None
    proxy_username: str | None
    proxy_password: str | None
    proxy_bypass: str | None

    # [dom_parsing]
    highlight_elements: bool
    focus_element: int
    viewport_expansion: int
    enable_pointer_elements: bool

    # [playwright wait/timeout]
    timeout_goto_ms: int
    timeout_default_ms: int
    timeout_action_ms: int
    timeout_evaluate_js_ms: int
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
        with DEFAULT_CONFIG_PATH.open("rb") as f:
            toml_data = tomllib.load(f)

        path = os.getenv("NOTTE_CONFIG_PATH")

        if path is not None:
            path = Path(path)
            if not path.exists():
                raise FileNotFoundError(f"Config file not found: {path}")

            # load external config
            with path.open("rb") as f:
                external_toml_data = tomllib.load(f)

            # Config files written for older versions may still set keys that were removed (e.g. the
            # agent and LLM settings of notte 1.x): warn and skip them instead of failing.
            unknown = sorted(set(external_toml_data) - set(cls.model_fields))
            if unknown:
                logger.warning(f"Ignoring unknown keys in config file {path}: {', '.join(unknown)}")
                external_toml_data = {k: v for k, v in external_toml_data.items() if k not in unknown}

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
    verbose: bool
    logging_mode: ErrorMode

    # [browser]
    headless: bool
    user_agent: str | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    cdp_url: str | None = None
    browser_type: BrowserType
    browser_backend: BrowserBackend
    web_security: bool
    custom_devtools_frontend: str | None = None
    debug_port: int | None = None
    chrome_args: list[str] | None = None
    raise_on_session_execution_failure: bool
    evaluate_js_max_result_bytes: int = Field(default=16 * 1024 * 1024, gt=0)
    evaluate_js_max_result_values: int = Field(default=50_000, gt=0)

    # [error]
    raise_condition: RaiseCondition

    # [proxy]
    proxy_host: str | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None
    proxy_bypass: str | None = None

    # [dom_parsing]
    highlight_elements: bool
    focus_element: int
    viewport_expansion: int
    enable_pointer_elements: bool

    # [playwright wait/timeout]
    timeout_goto_ms: int
    timeout_default_ms: int
    timeout_action_ms: int
    timeout_evaluate_js_ms: int
    wait_retry_snapshot_ms: int
    wait_short_ms: int
    empty_page_max_retry: int

    # [misc]
    enable_profiling: bool

    @override
    def model_post_init(self, context: Any, /) -> None:
        LoggingSetup.set_logger_mode(self.logging_mode)

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
# 2. Root config structure should be global for all packages (notte-core, notte-sdk, notte-browser) and should therefore be put in notte-core
# 3. Users that want extra config options can create their own config file and pass it to the from_toml method. The rule is that the new params override the defaul one
#### -> This is very good because we can enforce headless=True on the CICD and docker images with this without breaking the config for the users
# 4. If some components require a parameter to be set to a certain value, we can add a model_validator to the config class that will check that the parameter is set to the correct value.


config = NotteConfig.from_toml()
