from pathlib import Path
from typing import Any, Self

import toml
from pydantic import BaseModel, model_validator

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


class TomlConfig(BaseModel):
    @classmethod
    def from_toml(cls, path: str | Path | None = None) -> Self:
        """Load settings from a TOML file."""

        # load default config
        with DEFAULT_CONFIG_PATH.open("r") as f:
            toml_data = toml.load(f)

        if path is not None:
            path = Path(path)
            if not path.exists():
                raise FileNotFoundError(f"Config file not found: {path}")

            # load external config
            with path.open("r") as f:
                external_toml_data = toml.load(f)

            # merge configs
            toml_data = {**toml_data, **external_toml_data}

        return cls.model_validate(toml_data)


class NotteConfig(BaseModel):
    # [log]
    level: str
    verbose: bool

    # [llm]
    reasoning_model: str
    max_history_tokens: int | None
    structured_output_retries: int
    nb_retries: str
    clip_tokens: int

    # [browser]
    headless: bool
    user_agent: str | None
    viewport_width: int | None
    viewport_height: int | None
    browser_type: str
    web_security: bool
    cdp_debug: bool
    custom_devtools_frontend: str | None

    # [perception]
    perception_enabled: bool
    perception_model: str | None  # if none use reasoning_model

    # [scraping]
    auto_scrape: bool
    use_llm: bool
    rendering: str

    # [error]
    max_error_length: int
    raise_condition: str
    max_consecutive_failures: int

    # [proxy]
    proxy_host: str | None
    proxy_port: int | None
    proxy_username: str | None
    proxy_password: str | None

    # [agent]
    max_steps: int
    max_actions_per_step: int
    history_type: str
    human_in_the_loop: bool
    use_vision: bool


# DESIGN CHOICES after discussion with the leo
# 1. flat config structure with comments like # [browser] to structure the file
# 2. Root config structure should be global for all packages (notte-core, notte-agent, notte-browser) and should therefore be put in notte-core
# 3. Users that want extra config options can create their own config file and pass it to the from_toml method. The rule is that the new params override the defaul one
#### -> This is very good because we can enforce headless=True on the CICD and docker images with this without breaking the config for the users
# 4. If some agents required a parameter to be set to a certain value, we can add a model_validator to the config class that will check that the parameter is set to the correct value.
# 5. For computed fields such as `max_history_token` if the user does not set it, we use our computed value otherwise we default to the user value.


class FalcoConfig(TomlConfig):
    perception_enabled: bool = False
    auto_scrape: bool = False

    @model_validator(mode="before")
    def check_perception(self):
        if not self.perception_enabled:
            raise ValueError("Perception is required for falco. Don't set this argument to another value.")

    @model_validator(mode="before")
    def check_auto_scrape(self):
        if self.auto_scrape:
            raise ValueError("Auto scrape is not allowed for falco. Don't set this argument to another value.")
