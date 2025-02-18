from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from enum import StrEnum
from typing import Any, ClassVar, get_type_hints

from pydantic import BaseModel

from notte.env import NotteEnvConfig


class RaiseCondition(StrEnum):
    """How to raise an error when the agent fails to complete a step.

    Either immediately upon failure, after retry, or never.
    """

    IMMEDIATELY = "immediately"
    RETRY = "retry"
    NEVER = "never"


class AgentConfig(BaseModel):
    env: NotteEnvConfig
    reasoning_model: str = "openai/gpt-4o"
    include_screenshot: bool = False
    max_history_tokens: int = 16000
    max_error_length: int = 500
    raise_condition: RaiseCondition = RaiseCondition.RETRY
    max_consecutive_failures: int = 3

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

    @classmethod
    def create_parser(cls) -> ArgumentParser:
        """Creates an ArgumentParser with all the fields from the config."""
        parser = ArgumentParser()
        hints = get_type_hints(cls)

        for field_name, field_info in cls.model_fields.items():
            field_type = hints.get(field_name)
            if isinstance(field_type, ClassVar):  # type: ignore
                continue

            default = field_info.default  # type: ignore
            help_text = field_info.description or ""
            arg_type = cls._get_arg_type(field_type)  # type: ignore

            _ = parser.add_argument(
                f"--{field_name.replace('_', '-')}",
                type=arg_type,  # type: ignore
                default=default,
                help=help_text,
            )

        return parser

    @classmethod
    def from_args(cls, args: Namespace) -> "AgentConfig":
        """Creates an AgentConfig from a Namespace of arguments."""
        return cls(**vars(args))
