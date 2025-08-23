import typing

from notte_browser.session import NotteSession
from notte_browser.tools.base import BaseTool
from notte_core.common.config import NotteConfig
from notte_core.credentials.base import BaseVault
from notte_core.trajectory import Trajectory
from notte_sdk.types import AgentCreateRequest, AgentCreateRequestDict

from notte_agent.agent import NotteAgent
from notte_agent.falco.perception import FalcoPerception
from notte_agent.falco.prompt import FalcoPrompt


class FalcoAgent(NotteAgent):
    def __init__(
        self,
        session: NotteSession,
        vault: BaseVault | None = None,
        tools: list[BaseTool] | None = None,
        trajectory: Trajectory | None = None,
        **data: typing.Unpack[AgentCreateRequestDict],
    ):
        config: NotteConfig = NotteConfig.from_toml(**data)
        _ = AgentCreateRequest.model_validate(data)
        super().__init__(
            prompt=FalcoPrompt(tools=tools),
            perception=FalcoPerception(),
            config=config,
            session=session,
            trajectory=trajectory,
            vault=vault,
        )
