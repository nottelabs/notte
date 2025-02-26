from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from enum import StrEnum
from typing import Any, ClassVar, TypeVar, get_origin, get_type_hints

from pydantic import BaseModel, Field

from notte.env import NotteEnvConfig

T = TypeVar("T", bound="AgentConfig")


class RaiseCondition(StrEnum):
    """How to raise an error when the agent fails to complete a step.

    Either immediately upon failure, after retry, or never.
    """

    IMMEDIATELY = "immediately"
    RETRY = "retry"
    NEVER = "never"


class AgentConfig(BaseModel):
    env: NotteEnvConfig
    reasoning_model: str = Field(
        default="openai/gpt-4o", description="The model to use for reasoning (i.e taking actions)."
    )
    include_screenshot: bool = Field(default=False, description="Whether to include a screenshot in the response.")
    max_history_tokens: int = Field(
        default=16000,
        description="The maximum number of tokens in the history. When the history exceeds this limit, the oldest messages are discarded.",
    )
    max_error_length: int = Field(
        default=500, description="The maximum length of an error message to be forwarded to the reasoning model."
    )
    raise_condition: RaiseCondition = Field(
        default=RaiseCondition.RETRY, description="How to raise an error when the agent fails to complete a step."
    )
    max_consecutive_failures: int = Field(
        default=3, description="The maximum number of consecutive failures before the agent gives up."
    )

    def groq(self) -> "AgentConfig":
        self.reasoning_model = "groq/llama-3.3-70b-versatile"
        return self

    def openai(self) -> "AgentConfig":
        self.reasoning_model = "openai/gpt-4o"
        return self

    def cerebras(self) -> "AgentConfig":
        self.reasoning_model = "cerebras/llama-3.3-70b"
        return self

    def use_vision(self) -> "AgentConfig":
        self.include_screenshot = True
        return self

    def dev_mode(self) -> "AgentConfig":
        self.raise_condition = RaiseCondition.IMMEDIATELY
        self.max_error_length = 1000
        self.env = self.env.dev_mode()
        return self

    def map_env(self, env: Callable[[NotteEnvConfig], NotteEnvConfig]) -> "AgentConfig":
        self.env = env(self.env)
        return self

    @staticmethod
    def _get_arg_type(python_type: Any) -> Any:
        """Maps Python types to argparse types."""
        type_map = {
            str: str,
            int: int,
            float: float,
            bool: bool,
        }
        return type_map.get(python_type, str)

    @staticmethod
    def create_base_parser() -> ArgumentParser:
        """Creates a base ArgumentParser with all the fields from the config."""
        parser = ArgumentParser()
        _ = parser.add_argument(
            "--env.headless", type=bool, default=False, help="Whether to run the browser in headless mode."
        )
        _ = parser.add_argument(
            "--env.perception_model", type=str, default=None, help="The model to use for perception."
        )
        _ = parser.add_argument(
            "--env.max_steps", type=int, default=20, help="The maximum number of steps the agent can take."
        )
        return parser

    @classmethod
    def create_parser(cls) -> ArgumentParser:
        """Creates an ArgumentParser with all the fields from the config."""
        parser = cls.create_base_parser()
        hints = get_type_hints(cls)

        for field_name, field_info in cls.model_fields.items():
            if field_name == "env":
                continue
            field_type = hints.get(field_name)
            if get_origin(field_type) is ClassVar:
                continue

            default = field_info.default
            help_text = field_info.description or "no description available"
            arg_type = cls._get_arg_type(field_type)

            _ = parser.add_argument(
                f"--{field_name.replace('_', '-')}",
                type=arg_type,
                default=default,
                help=f"{help_text} (default: {default})",
            )

        return parser

    @classmethod
    def from_args(cls: type[T], args: Namespace) -> T:
        """Creates an AgentConfig from a Namespace of arguments.

        The return type will match the class that called this method.
        """
        env_args = {k: v for k, v in vars(args).items() if k.startswith("env.")}
        env_config = NotteEnvConfig(**env_args)
        return cls(**vars(args), env=env_config)
