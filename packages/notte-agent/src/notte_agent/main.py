import asyncio
from collections.abc import Callable

from loguru import logger
from notte_browser.session import NotteSession
from notte_browser.window import BrowserWindow
from notte_core.browser.allowlist import ActionAllowList, URLAllowList
from notte_core.credentials.base import BaseVault
from notte_core.llms.engine import LlmModel
from notte_sdk.types import DEFAULT_MAX_NB_STEPS, AgentCreateRequest

from notte_agent.common.base import BaseAgent
from notte_agent.common.notifier import BaseNotifier, NotifierAgent
from notte_agent.common.types import AgentResponse
from notte_agent.falco.agent import FalcoAgent, FalcoAgentConfig
from notte_agent.falco.types import StepAgentOutput


class Agent:
    def __init__(
        self,
        headless: bool = False,
        reasoning_model: LlmModel = LlmModel.default(),  # type: ignore[reportCallInDefaultInitializer]
        max_steps: int = DEFAULT_MAX_NB_STEPS,
        use_vision: bool = True,
        # /!\ web security is disabled by default to increase agent performance
        # turn it off if you need to input confidential information on trajectories
        web_security: bool = False,
        chrome_args: list[str] | None = None,
        vault: BaseVault | None = None,
        notifier: BaseNotifier | None = None,
        session: NotteSession | None = None,
        window: BrowserWindow | None = None,
        action_allow_list: ActionAllowList | None = None,
        url_allow_list: URLAllowList | None = None,
    ):
        # just validate the request to create type dependency
        _ = AgentCreateRequest(
            reasoning_model=reasoning_model,
            use_vision=use_vision,
            max_steps=max_steps,
            vault_id=None,
        )

        if url_allow_list is None:
            url_allow_list = URLAllowList()

        if action_allow_list is None:
            action_allow_list = ActionAllowList()

        self.config: FalcoAgentConfig = (
            FalcoAgentConfig()
            .use_vision(use_vision)
            .model(reasoning_model, deep=True)
            .map_session(
                lambda session: (
                    session.agent_mode()
                    .steps(max_steps)
                    .headless(headless)
                    .web_security(web_security)
                    .set_chrome_args(chrome_args)
                    .set_url_allow_list(url_allow_list)
                    .set_action_allow_list(action_allow_list)
                )
            )
        )
        self.vault: BaseVault | None = vault
        self.notifier: BaseNotifier | None = notifier
        self.window: BrowserWindow | None = window
        self.session: NotteSession | None = session

        self.persist_session: bool = False  # make the session continue after agent ran

        if self.window is not None and self.session is not None:
            raise ValueError("Can't set both session and window")

    async def create_agent(
        self,
        step_callback: Callable[[str, StepAgentOutput], None] | None = None,
    ) -> BaseAgent:
        if self.session is None:
            self.session = NotteSession(config=self.config.session, window=self.window)
        else:
            logger.warning("Session was already created before passing to agent, ignoring session parameters")
            self.persist_session = True

        # need to start session before passing window
        await self.session.start()

        agent = FalcoAgent(
            config=self.config,
            vault=self.vault,
            window=self.session.window,
            step_callback=step_callback,
        )
        if self.notifier:
            agent = NotifierAgent(agent, notifier=self.notifier)
        return agent

    async def arun(self, task: str, url: str | None = None) -> AgentResponse:
        try:
            agent = await self.create_agent()

            if self.session is None:
                raise ValueError("Session could not be created")

            return await agent.run(task, url=url)
        finally:
            if self.session is not None and not self.persist_session:
                await self.session.stop()

    def run(self, task: str, url: str | None = None) -> AgentResponse:
        return asyncio.run(self.arun(task, url=url))
