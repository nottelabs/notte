from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from enum import StrEnum
from typing import Any, ClassVar, Self, get_origin, get_type_hints

from notte_browser.session import NotteSessionConfig
from notte_core.common.config import FrozenConfig
from notte_core.llms.engine import LlmModel
from notte_sdk.types import DEFAULT_MAX_NB_STEPS
from pydantic import Field, model_validator


class RaiseCondition(StrEnum):
    """How to raise an error when the agent fails to complete a step.

    Either immediately upon failure, after retry, or never.
    """

    IMMEDIATELY = "immediately"
    RETRY = "retry"
    NEVER = "never"


class DefaultAgentArgs(StrEnum):
    SESSION_DISABLE_WEB_SECURITY = "disable_web_security"
    SESSION_HEADLESS = "headless"
    SESSION_PERCEPTION_MODEL = "perception_model"
    SESSION_MAX_STEPS = "max_steps"

    def with_prefix(self: Self, prefix: str = "session") -> str:
        return f"{prefix}.{self.value}"


class AgentConfig(FrozenConfig, ABC):
    # make session private to avoid exposing the NotteSessionConfig class
    session: NotteSessionConfig = Field(init=False)
    reasoning_model: LlmModel = Field(
        default_factory=lambda: LlmModel.default(), description="The model to use for reasoning (i.e taking actions)."
    )
    include_screenshot: bool = Field(default=False, description="Whether to include a screenshot in the response.")
    max_history_tokens: int | None = Field(
        default=None,
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
    force_session: bool | None = Field(
        default=None,
        description="Whether to allow the user to set the session or not.",
    )
    human_in_the_loop: bool = Field(default=False, description="Whether to enable human-in-the-loop mode.")

    @classmethod
    @abstractmethod
    def default_session(cls) -> NotteSessionConfig:
        raise NotImplementedError("Subclasses must implement this method")

    @model_validator(mode="before")
    @classmethod
    def set_session(cls, values: dict[str, Any]) -> dict[str, Any]:
        if "session" in values:
            if "force_session" in values and values["force_session"]:
                del values["force_session"]
                return values
            raise ValueError("Session should not be set by the user. Set `default_session` instead.")
        values["session"] = cls.default_session()  # Set the session field using the subclass's method
        return values

    def groq(self: Self, deep: bool = True) -> Self:
        return self.model(LlmModel.groq, deep=deep)

    def openai(self: Self, deep: bool = True) -> Self:
        return self.model(LlmModel.openai, deep=deep)

    def gemini(self: Self, deep: bool = True) -> Self:
        return self.model(LlmModel.gemini, deep=deep)

    def cerebras(self: Self, deep: bool = True) -> Self:
        return self.model(LlmModel.cerebras, deep=deep)

    def model(self: Self, model: LlmModel, deep: bool = True) -> Self:
        config = self._copy_and_validate(reasoning_model=model, max_history_tokens=LlmModel.context_length(model))
        if deep:
            config = config.map_session(lambda session: session.model(model))
        return config

    def use_vision(self: Self, value: bool = True) -> Self:
        return self._copy_and_validate(include_screenshot=value)

    def set_human_in_the_loop(self: Self, value: bool = True) -> Self:
        return self._copy_and_validate(human_in_the_loop=value)

    def dev_mode(self: Self) -> Self:
        return self._copy_and_validate(
            raise_condition=RaiseCondition.IMMEDIATELY,
            max_error_length=1000,
            session=self.session.dev_mode(),
            force_session=True,
        )

    def set_raise_condition(self: Self, value: RaiseCondition) -> Self:
        return self._copy_and_validate(raise_condition=value)

    def map_session(self: Self, ft: Callable[[NotteSessionConfig], NotteSessionConfig]) -> Self:
        return self._copy_and_validate(session=ft(self.session), force_session=True)

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
            f"--{DefaultAgentArgs.SESSION_HEADLESS.with_prefix()}",
            action="store_true",
            help="Whether to run the browser in headless mode.",
        )
        _ = parser.add_argument(
            f"--{DefaultAgentArgs.SESSION_DISABLE_WEB_SECURITY.with_prefix()}",
            action="store_true",
            help="Whether disable web security.",
        )
        _ = parser.add_argument(
            f"--{DefaultAgentArgs.SESSION_PERCEPTION_MODEL.with_prefix()}",
            type=str,
            default=LlmModel.default(),
            help="The model to use for perception.",
        )
        _ = parser.add_argument(
            f"--{DefaultAgentArgs.SESSION_MAX_STEPS.with_prefix()}",
            type=int,
            default=DEFAULT_MAX_NB_STEPS,
            help="The maximum number of steps the agent can take.",
        )
        return parser

    @classmethod
    def create_parser(cls) -> ArgumentParser:
        """Creates an ArgumentParser with all the fields from the config."""
        parser = cls.create_base_parser()
        hints = get_type_hints(cls)

        for field_name, field_info in cls.model_fields.items():
            if field_name == "session":
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
    def from_args(cls: type[Self], args: Namespace) -> Self:
        """Creates an AgentConfig from a Namespace of arguments.

        The return type will match the class that called this method.
        """
        disallowed_args = ["task", "session.window.headless"]

        session_args = {
            k.replace("session.", "").replace("-", "_"): v
            for k, v in vars(args).items()
            if k.startswith("session.") and k not in disallowed_args
        }
        agent_args = {
            k.replace("-", "_"): v
            for k, v in vars(args).items()
            if not k.startswith("session.") and k not in disallowed_args
        }

        def update_session(session: NotteSessionConfig) -> NotteSessionConfig:
            operations: list[Callable[[NotteSessionConfig], NotteSessionConfig]] = []
            if DefaultAgentArgs.SESSION_HEADLESS in session_args:
                headless = session_args[DefaultAgentArgs.SESSION_HEADLESS]
                operations.append(lambda session: session.headless(headless))
                del session_args[DefaultAgentArgs.SESSION_HEADLESS]
            if DefaultAgentArgs.SESSION_DISABLE_WEB_SECURITY in session_args:
                disable_web_security = session_args[DefaultAgentArgs.SESSION_DISABLE_WEB_SECURITY]
                operations.append(
                    lambda session: session.disable_web_security()
                    if disable_web_security
                    else session.enable_web_security()
                )
                del session_args[DefaultAgentArgs.SESSION_DISABLE_WEB_SECURITY]

            session = session._copy_and_validate(**session_args)
            for operation in operations:
                session = operation(session)
            return session

        return cls(**agent_args).map_session(update_session)
