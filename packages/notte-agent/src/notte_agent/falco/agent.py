import typing
from collections.abc import Callable

from loguru import logger
from notte_browser.session import NotteSession
from notte_browser.window import BrowserWindow
from notte_core.agent_types import AgentStepResponse
from notte_core.common.config import NotteConfig
from notte_core.credentials.base import BaseVault
from notte_core.storage import BaseStorage
from notte_sdk.types import AgentCreateRequest, AgentCreateRequestDict
from pydantic import field_validator

from notte_agent.agent import NotteAgent
from notte_agent.falco.perception import FalcoPerception
from notte_agent.falco.prompt import FalcoPrompt


class FalcoConfig(NotteConfig):
    enable_perception: bool = False

    @field_validator("enable_perception")
    @classmethod
    def check_perception(cls, value: bool) -> bool:
        if value:
            logger.warning("Perception should be disabled for falco. Don't set this argument to `True`.")
        return False


class FalcoAgent(NotteAgent):
    def __init__(
        self,
        window: BrowserWindow,
        storage: BaseStorage | None = None,
        vault: BaseVault | None = None,
        step_callback: Callable[[AgentStepResponse], None] | None = None,
        **data: typing.Unpack[AgentCreateRequestDict],
    ):
        _ = AgentCreateRequest.model_validate(data)
        config: FalcoConfig = FalcoConfig.from_toml(**data)
        session = NotteSession(window=window, storage=storage, enable_perception=False)
        super().__init__(
            prompt=FalcoPrompt(),
            perception=FalcoPerception(),
            config=config,
            session=session,
            vault=vault,
            step_callback=step_callback,
        )
