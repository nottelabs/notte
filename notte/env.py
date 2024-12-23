import asyncio
from typing import Literal, Unpack, final

from loguru import logger

from notte.actions.base import Action, ActionParameterValue, SpecialAction
from notte.actions.code import process_action_code
from notte.browser.context import Context
from notte.browser.driver import BrowserArgs, BrowserDriver
from notte.browser.observation import Observation
from notte.browser.snapshot import BrowserSnapshot
from notte.common.logging import timeit
from notte.common.resource import AsyncResource
from notte.llms.service import LLMService
from notte.pipe.data_scraping import DataScrapingPipe
from notte.pipe.main import ContextToActionSpacePipe
from notte.pipe.preprocessing.a11y.pipe import ActionA11yPipe
from notte.pipe.resolution import ActionNodeResolutionPipe


@final
class BrowserSnapshotToContextPipe:
    @staticmethod
    def forward(snapshot: BrowserSnapshot) -> Context:
        return ActionA11yPipe.forward(snapshot)


@final
class ExecutionPipe:
    @staticmethod
    async def forward(
        action: Action,
        params: list[ActionParameterValue],
        context: Context,
        browser: BrowserDriver,
        enter: bool = False,
    ) -> BrowserSnapshot:
        exec_actions = await ActionNodeResolutionPipe(browser).forward(action, params, context)
        action = process_action_code(exec_actions, context, generated=False)
        return await browser.execute_action(action, context, enter)


class NotteEnv(AsyncResource):
    def __init__(
        self,
        max_steps: int | None = None,
        browser: BrowserDriver | None = None,
        trajectory: list[Observation] | None = None,
        llmserve: LLMService | None = None,
        **browser_kwargs: Unpack[BrowserArgs],
    ) -> None:
        self._max_steps: int | None = max_steps
        self._browser: BrowserDriver = browser or BrowserDriver(**browser_kwargs)
        super().__init__(self._browser)
        self._trajectory: list[Observation] = trajectory or []
        self._context: Context | None = None
        self._context_to_action_space_pipe: ContextToActionSpacePipe = ContextToActionSpacePipe(llmserve=llmserve)
        self._data_scraping_pipe: DataScrapingPipe = DataScrapingPipe(llmserve=llmserve)

    @property
    def context(self) -> Context:
        if self._context is None:
            raise ValueError("Need to observe first to get a context.")
        return self._context

    @property
    def previous_actions(self) -> list[Action] | None:
        # This function is always called after trajectory.append(preobs)
        # —This means trajectory[-1] is always the "current (pre)observation"
        # And trajectory[-2] is the "previous observation" we're interested in.
        if len(self._trajectory) <= 1:
            return None
        previous_obs: Observation = self._trajectory[-2]
        if not previous_obs.has_space():
            return None  # we don't have a space for pre-observations
        if self.obs.clean_url != previous_obs.clean_url:
            return None  # the page has significantly changed
        return previous_obs.space.actions(status="all")

    @property
    def obs(self) -> Observation:
        if len(self._trajectory) <= 0:
            raise ValueError("Need to observe first to get a context.")
        return self._trajectory[-1]

    # ---------------------------- observe, step functions ----------------------------

    def _preobserve(self, snapshot: BrowserSnapshot) -> Observation:
        if self._max_steps is not None and len(self._trajectory) >= self._max_steps:
            raise ValueError(f"Max steps reached: {self._max_steps}")
        self._context = BrowserSnapshotToContextPipe.forward(snapshot)
        preobs = Observation.from_snapshot(snapshot)
        self._trajectory.append(preobs)
        return preobs

    def _obslisting(self) -> Observation:
        self.obs.space = self._context_to_action_space_pipe.forward(self.context, self.previous_actions)
        return self.obs

    @timeit("goto")
    async def goto(self, url: str | None) -> Observation:
        snapshot = await self._browser.goto(url)
        return self._preobserve(snapshot)

    @timeit("observe")
    async def observe(self, url: str | None = None) -> Observation:
        _ = await self.goto(url)
        logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
        logger.debug(f"ℹ️ context inodes IDs: {[node.id for node in self.context.interaction_nodes()]}")
        return self._obslisting()

    @timeit("execute")
    async def execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        if SpecialAction.is_special(action_id):
            return await self._execute_special(action_id, params)  # type: ignore
        if action_id not in [inode.id for inode in self.context.interaction_nodes()]:
            raise ValueError(f"action {action_id} not found in context")
        action, _params = self._parse_env(action_id, params)
        enter = enter if enter is not None else action.id.startswith("I")
        snapshot = await ExecutionPipe.forward(action, _params, self.context, self._browser, enter=enter)
        logger.info(f"🌌 action {action_id} executed in browser")
        return self._preobserve(snapshot)

    @timeit("execute_special")
    async def _execute_special(
        self,
        action_id: Literal["S1", "S2", "S3", "S4", "S5", "S6", "S7"],
        params: dict[str, str] | str | None = None,
    ) -> Observation:
        if not SpecialAction.is_special(action_id):
            raise ValueError(f"action {action_id} is not a special action")
        _, _params = self._parse_env(action_id, params)
        match action_id:
            case "S1":
                if len(_params) == 0:
                    raise ValueError("Special action S1 requires a parameter")
                return await self.goto(_params[0].value)
            case "S2":
                return await self.scrape()
            case "S3":
                snapshot = await self._browser.snapshot(screenshot=True)
            case "S4":
                snapshot = await self._browser.back()
            case "S5":
                snapshot = await self._browser.forward()
            case "S6":
                if len(_params) == 0:
                    raise ValueError("Special action S6 requires a parameter")
                await self._browser.wait(int(_params[0].value))
                snapshot = await self._browser.snapshot()
            case "S7":
                snapshot = await self._browser.snapshot()
                await self._browser.close()
        logger.info(f"🌌 special action {action_id} executed in browser")
        return self._preobserve(snapshot)

    @timeit("step")
    async def step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        _ = await self.execute(action_id, params, enter=enter)
        logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
        logger.debug(f"ℹ️ context inodes IDs: {[node.id for node in self.context.interaction_nodes()]}")
        return self._obslisting()

    @timeit("scrape")
    async def scrape(self, url: str | None = None) -> Observation:
        if url is not None:
            _ = await self.goto(url)
        self.obs.data = await self._data_scraping_pipe.forward_async(self.context)
        return self.obs

    @timeit("god")
    async def god(self) -> Observation:
        space, data = await asyncio.gather(
            self._context_to_action_space_pipe.forward_async(self.context, self.previous_actions),
            self._data_scraping_pipe.forward_async(self.context),
        )
        self.obs.space = space
        self.obs.data = data
        return self.obs

    @timeit("reset")
    async def reset(self, url: str) -> Observation:
        self._trajectory = []
        self._context = None
        return await self.goto(url)

    # ------------------------------ Private ---------------------------------------

    def _parse_env(
        self, action_id: str, params: dict[str, str] | str | None = None
    ) -> tuple[Action, list[ActionParameterValue]]:
        if isinstance(params, str):
            params = {"value": params}
        _params: list[ActionParameterValue] = []
        if params is not None:
            _params = [
                ActionParameterValue(
                    parameter_name=name,
                    value=value,
                )
                for name, value in params.items()
            ]
        return (
            Action(id=action_id, description="ID only", category="", status="valid"),
            _params,
        )
