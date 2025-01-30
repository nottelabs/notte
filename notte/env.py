import asyncio
from typing import Unpack

from loguru import logger
from pydantic import BaseModel

from notte.actions.base import (
    Action,
    ActionParameter,
    ActionParameterValue,
    SpecialAction,
)
from notte.browser.driver import BrowserConfig, BrowserDriver
from notte.browser.observation import Observation, TrajectoryProgress
from notte.browser.pool import BrowserPool
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.browser.snapshot import BrowserSnapshot
from notte.common.logging import timeit
from notte.common.resource import AsyncResource
from notte.controller.action_proxy import NotteActionProxy
from notte.controller.actions import BrowserActionId
from notte.controller.base import BrowserController
from notte.errors.actions import InvalidActionError
from notte.errors.env import MaxStepsReachedError, NoContextObservedError
from notte.llms.service import LLMService
from notte.pipe.main import (
    BaseContextToActionSpacePipe,
    ContextToActionSpaceConfig,
    ContextToActionSpacePipe,
)
from notte.pipe.preprocessing.pipe import PreprocessingType, ProcessedSnapshotPipe
from notte.pipe.resolution import ActionNodeResolutionPipe
from notte.pipe.scraping.config import ScrapingConfig
from notte.pipe.scraping.pipe import DataScrapingPipe
from notte.sdk.types import (
    DEFAULT_MAX_NB_STEPS,
    PaginationObserveRequest,
    PaginationObserveRequestDict,
)


class NotteEnvConfig(BaseModel):
    max_steps: int = DEFAULT_MAX_NB_STEPS
    processing_type: PreprocessingType = PreprocessingType.A11Y
    browser: BrowserConfig = BrowserConfig()
    scraping: ScrapingConfig = ScrapingConfig()
    main_listing: ContextToActionSpaceConfig = ContextToActionSpaceConfig()
    observe_max_retry_after_snapshot_update: int = 2


# @final
# class ExecutionPipe:
#     @staticmethod
#     async def forward(
#         action: Action,
#         params: list[ActionParameterValue],
#         context: ProcessedBrowserSnapshot,
#         browser: BrowserDriver,
#         enter: bool,
#     ) -> BrowserSnapshot:
#         exec_actions = await ActionNodeResolutionPipe(browser).forward(action, params, context)
#         action = process_action_code(exec_actions, context, generated=False)
#         return await browser.execute_action(action, context, enter)


class NotteEnv(AsyncResource):
    def __init__(
        self,
        config: NotteEnvConfig | None = None,
        headless: bool = False,
        browser: BrowserDriver | None = None,
        pool: BrowserPool | None = None,
        llmserve: LLMService | None = None,
    ) -> None:
        self._config: NotteEnvConfig = config or NotteEnvConfig()
        self._config.browser.headless = headless
        self._browser: BrowserDriver = browser or BrowserDriver(pool=pool, config=self._config.browser)
        super().__init__(self._browser)
        self.controller: BrowserController = BrowserController(self._browser)

        self._trajectory: list[Observation] = []
        self._context: ProcessedBrowserSnapshot | None = None
        self._context_to_action_space_pipe: BaseContextToActionSpacePipe = ContextToActionSpacePipe(
            llmserve=llmserve, config=self._config.main_listing
        )
        self._data_scraping_pipe: DataScrapingPipe = DataScrapingPipe(llmserve=llmserve, browser=self._browser)

    @property
    def context(self) -> ProcessedBrowserSnapshot:
        if self._context is None:
            raise NoContextObservedError()
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
            raise NoContextObservedError()
        return self._trajectory[-1]

    def progress(self) -> TrajectoryProgress:
        return TrajectoryProgress(
            max_steps=self._config.max_steps,
            current_step=len(self._trajectory),
        )

    # ---------------------------- observe, step functions ----------------------------

    def _preobserve(self, snapshot: BrowserSnapshot) -> Observation:
        if len(self._trajectory) >= self._config.max_steps:
            raise MaxStepsReachedError(max_steps=self._config.max_steps)
        self._context = ProcessedSnapshotPipe.forward(snapshot, type=self._config.processing_type)
        preobs = Observation.from_snapshot(snapshot, progress=self.progress())
        self._trajectory.append(preobs)
        return preobs

    async def _observe(
        self,
        pagination: PaginationObserveRequest,
        retry: int,
    ) -> Observation:
        self.obs.space = self._context_to_action_space_pipe.forward(
            self.context,
            self.previous_actions,
            pagination=pagination,
        )
        # TODO: improve this
        # Check if the snapshot has changed since the beginning of the trajectory
        # if it has, it means that the page was not fully loaded and that we should restart the oblisting
        check_snapshot = await self._browser.snapshot()
        if not self.context.snapshot.compare_with(check_snapshot) and retry > 0:
            logger.warning("Snapshot changed since the beginning of the action listing, retrying to observe again")
            _ = self._preobserve(check_snapshot)
            return await self._observe(retry=retry - 1, pagination=pagination)

        if self.obs.space.category is not None and self.obs.space.category.is_data() and not self.obs.has_data():
            self.obs.data = await self._data_scraping_pipe.forward(self.context, self._config.scraping)
        return self.obs

    @timeit("goto")
    async def goto(self, url: str | None) -> Observation:
        snapshot = await self._browser.goto(url)
        return self._preobserve(snapshot)

    @timeit("observe")
    async def observe(
        self,
        url: str | None = None,
        **pagination: Unpack[PaginationObserveRequestDict],
    ) -> Observation:
        _ = await self.goto(url)
        logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
        logger.debug(f"ℹ️ context inodes IDs: {[node.id for node in self.context.interaction_nodes()]}")
        return await self._observe(
            pagination=PaginationObserveRequest.model_validate(pagination),
            retry=self._config.observe_max_retry_after_snapshot_update,
        )

    @timeit("execute")
    async def execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        if not SpecialAction.is_special(action_id):
            # Scrape action is a special case
            if action_id == BrowserActionId.SCRAPE:
                return await self.scrape()
        elif action_id not in [inode.id for inode in self.context.interaction_nodes()]:
            raise InvalidActionError(action_id=action_id, reason=f"action '{action_id}' not found in page context.")
        action, _params = self._parse_env(action_id, params)

        enter = enter if enter is not None else action.id.startswith("I")
        exec_action = await ActionNodeResolutionPipe(self._browser).forward(action, _params, self.context)
        browser_action = NotteActionProxy.forward_special(exec_action)
        snapshot = await self.controller.execute(browser_action)
        logger.info(f"🌌 action {action_id} executed in browser")
        return self._preobserve(snapshot)

    @timeit("step")
    async def step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
        **pagination: Unpack[PaginationObserveRequestDict],
    ) -> Observation:
        _ = await self.execute(action_id, params, enter=enter)
        logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
        logger.debug(f"ℹ️ context inodes IDs: {[node.id for node in self.context.interaction_nodes()]}")
        return await self._observe(
            pagination=PaginationObserveRequest.model_validate(pagination),
            retry=self._config.observe_max_retry_after_snapshot_update,
        )

    @timeit("scrape")
    async def scrape(
        self,
        url: str | None = None,
        only_main_content: bool = True,
        scrape_images: bool = False,
    ) -> Observation:
        if url is not None:
            _ = await self.goto(url)
        self._config.scraping.request.only_main_content = only_main_content
        self._config.scraping.request.scrape_images = scrape_images
        self.obs.data = await self._data_scraping_pipe.forward(
            self.context,
            self._config.scraping,
        )
        return self.obs

    @timeit("god")
    async def god(self, url: str | None = None, **pagination: Unpack[PaginationObserveRequestDict]) -> Observation:
        if url is not None:
            _ = await self.goto(url)
        _pagination = PaginationObserveRequest.model_validate(pagination)
        space, data = await asyncio.gather(
            self._context_to_action_space_pipe.forward_async(
                self.context, self.previous_actions, pagination=_pagination
            ),
            self._data_scraping_pipe.forward_async(self.context, self._config.scraping),
        )
        self.obs.space = space
        self.obs.data = data
        return self.obs

    @timeit("reset")
    async def reset(self) -> None:
        self._trajectory = []
        self._context = None
        return await self._browser.reset()

    # ------------------------------ Private ---------------------------------------

    def _parse_env(
        self, action_id: str, params: dict[str, str] | str | None = None
    ) -> tuple[Action, list[ActionParameterValue]]:
        if isinstance(params, str):
            params = {"value": params}
        _param_values: list[ActionParameterValue] = []
        _params: list[ActionParameter] = []
        if params is not None:
            _param_values = [
                ActionParameterValue(
                    parameter_name=name,
                    value=value,
                )
                for name, value in params.items()
            ]
            _params = [
                ActionParameter(
                    name=name,
                    type="string",
                )
                for name in params.keys()
            ]
        return (
            Action(
                id=action_id,
                description="ID only",
                category="",
                status="valid",
                params=_params,
            ),
            _param_values,
        )
