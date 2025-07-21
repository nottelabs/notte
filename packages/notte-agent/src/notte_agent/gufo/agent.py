import typing

from notte_browser.session import NotteSession
from notte_core.common.config import NotteConfig
from notte_core.credentials.base import BaseVault
from notte_sdk.types import AgentCreateRequest, AgentCreateRequestDict

from notte_agent.agent import NotteAgent
from notte_agent.gufo.perception import GufoPerception
from notte_agent.gufo.prompt import GufoPrompt


class GufoAgent(NotteAgent):
    def __init__(
        self,
        session: NotteSession,
        vault: BaseVault | None = None,
        **data: typing.Unpack[AgentCreateRequestDict],
    ):
        _ = AgentCreateRequest.model_validate(data)
        config: NotteConfig = NotteConfig.from_toml(**data)
        super().__init__(
            prompt=GufoPrompt(),
            perception=GufoPerception(),
            config=config,
            session=session,
            trajectory=session.trajectory.view(),
            vault=vault,
        )
