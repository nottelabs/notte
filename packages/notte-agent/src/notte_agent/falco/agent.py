import typing

from loguru import logger
from notte_browser.session import NotteSession
from notte_browser.tools.base import BaseTool
from notte_browser.window import BrowserWindow
from notte_core.agent_types import AgentStepResponse
from notte_core.common.config import NotteConfig
from notte_core.credentials.base import BaseVault
from notte_sdk.types import AgentCreateRequest, AgentCreateRequestDict

from notte_agent.agent import NotteAgent
from notte_agent.falco.perception import FalcoPerception
from notte_agent.falco.prompt import FalcoPrompt


class FalcoConfig(NotteConfig):
    pass


class FalcoAgent(NotteAgent):
    def __init__(
        self,
        session: NotteSession,
        vault: BaseVault | None = None,
        tools: list[BaseTool] | None = None,
        step_callback: Callable[[AgentStepResponse], None] | None = None,
        **data: typing.Unpack[AgentCreateRequestDict],
    ):
        _ = AgentCreateRequest.model_validate(data)
        config: FalcoConfig = FalcoConfig.from_toml(**data)
        session = NotteSession(window=window, storage=storage, enable_perception=False, tools=tools)
        super().__init__(
            prompt=FalcoPrompt(tools=tools),
            perception=FalcoPerception(),
            config=config,
            session=session,
            trajectory=session.trajectory.view(),
            vault=vault,
        )
