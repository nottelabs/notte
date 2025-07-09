import typing
from collections.abc import Callable

from notte_browser.session import NotteSession
from notte_browser.window import BrowserWindow
from notte_core.agent_types import AgentStepResponse
from notte_core.common.config import NotteConfig
from notte_core.credentials.base import BaseVault
from notte_sdk.types import AgentCreateRequest, AgentCreateRequestDict
from pydantic import field_validator

from notte_agent.agent import NotteAgent
from notte_agent.gufo.perception import GufoPerception
from notte_agent.gufo.prompt import GufoPrompt


class GufoConfig(NotteConfig):
    enable_perception: bool = True

    @field_validator("enable_perception")
    @classmethod
    def check_perception(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Perception should be enabled for gufo. Don't set this argument to `False`.")
        return value


class GufoAgent(NotteAgent):
    def __init__(
        self,
        window: BrowserWindow,
        vault: BaseVault | None = None,
        step_callback: Callable[[AgentStepResponse], None] | None = None,
        **data: typing.Unpack[AgentCreateRequestDict],
    ):
        _ = AgentCreateRequest.model_validate(data)
        config: GufoConfig = GufoConfig.from_toml(**data)
        session = NotteSession(window=window, enable_perception=True)
        super().__init__(
            prompt=GufoPrompt(),
            perception=GufoPerception(),
            config=config,
            session=session,
            vault=vault,
            step_callback=step_callback,
        )
