import asyncio
import datetime as dt
from collections.abc import Sequence
from typing import Unpack

from loguru import logger
from pydantic import BaseModel

from notte.actions.base import ExecutableAction
from notte.browser.driver import BrowserConfig, BrowserDriver
from notte.browser.observation import Observation, TrajectoryProgress
from notte.browser.pool import BrowserPool
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.browser.snapshot import BrowserSnapshot
from notte.common.logging import timeit
from notte.common.resource import AsyncResource
from notte.controller.actions import (
    BaseAction,
    BrowserActionId,
    GotoAction,
    ScrapeAction,
    WaitAction,
)
from notte.controller.base import BrowserController
from notte.errors.env import MaxStepsReachedError, NoContextObservedError
from notte.errors.processing import InvalidInternalCheckError
from notte.llms.service import LLMService
from notte.pipe.action.pipe import (
    ActionSpaceType,
    MainActionSpaceConfig,
    MainActionSpacePipe,
)
from notte.pipe.preprocessing.pipe import (
    PreprocessingConfig,
    PreprocessingType,
    ProcessedSnapshotPipe,
)
from notte.pipe.resolution.pipe import NodeResolutionPipe
from notte.pipe.scraping.pipe import DataScrapingPipe, ScrapingConfig, ScrapingType
from notte.sdk.types import (
    DEFAULT_MAX_NB_STEPS,
    PaginationParams,
    PaginationParamsDict,
    ScrapeParams,
    ScrapeParamsDict,
)


class ScrapeAndObserveParamsDict(ScrapeParamsDict, PaginationParamsDict):
    pass


class NotteEnvConfig(BaseModel):
    max_steps: int = DEFAULT_MAX_NB_STEPS
    preprocessing: PreprocessingConfig = PreprocessingConfig()
    browser: BrowserConfig = BrowserConfig()
    scraping: ScrapingConfig = ScrapingConfig()
    action: MainActionSpaceConfig = MainActionSpaceConfig()
    observe_max_retry_after_snapshot_update: int = 2
    nb_seconds_between_snapshots_check: int = 10
    auto_scrape: bool = True
    perception_model: str | None = None
    verbose: bool = False

    def dev_mode(self) -> "NotteEnvConfig":
        self.verbose = True
        self.browser.verbose = True
        self.action.verbose = True
        self.action.llm_tagging.verbose = True
        self.action.llm_tagging.listing.verbose = True
        self.action.llm_tagging.listing.rendering.verbose = True
        self.scraping.rendering.verbose = True
        self.preprocessing.a11y.pruning.verbose = True
        return self

    def user_mode(self) -> "NotteEnvConfig":
        self.verbose = True
        self.browser.verbose = True
        self.action.verbose = True
        self.action.llm_tagging.verbose = True
        self.action.llm_tagging.listing.verbose = True
        return self

    def groq(self) -> "NotteEnvConfig":
        self.perception_model = "groq/llama-3.3-70b-versatile"
        return self

    def openai(self) -> "NotteEnvConfig":
        self.perception_model = "openai/gpt-4o"
        return self

    def cerebras(self) -> "NotteEnvConfig":
        self.perception_model = "cerebras/llama-3.3-70b"
        return self

    def a11y(self) -> "NotteEnvConfig":
        self.preprocessing.type = PreprocessingType.A11Y
        return self

    def dom(self) -> "NotteEnvConfig":
        self.preprocessing.type = PreprocessingType.DOM
        return self

    def steps(self, max_steps: int | None = None) -> "NotteEnvConfig":
        self.max_steps = max_steps if max_steps is not None else DEFAULT_MAX_NB_STEPS
        return self

    def headless(self, value: bool | None = None) -> "NotteEnvConfig":
        self.browser.headless = value if value is not None else True
        return self

    def not_headless(self) -> "NotteEnvConfig":
        self.browser.headless = False
        return self

    def cdp(self, url: str) -> "NotteEnvConfig":
        self.browser.cdp_url = url
        return self

    def llm_action_tagging(self) -> "NotteEnvConfig":
        self.action.type = ActionSpaceType.LLM_TAGGING
        return self

    def llm_data_extract(self) -> "NotteEnvConfig":
        self.scraping.type = ScrapingType.LLM_EXTRACT
        return self

    def disable_web_security(self) -> "NotteEnvConfig":
        self.browser.disable_web_security = True
        return self

    def disable_auto_scrape(self) -> "NotteEnvConfig":
        self.auto_scrape = False
        return self

    def use_llm(self) -> "NotteEnvConfig":
        return self.llm_data_extract().llm_action_tagging()

    def disable_llm(self) -> "NotteEnvConfig":
        self.scraping.type = ScrapingType.SIMPLE
        self.action.type = ActionSpaceType.SIMPLE
        return self.dom().disable_auto_scrape()


class TrajectoryStep(BaseModel):
    obs: Observation
    action: BaseAction


class NotteEnv(AsyncResource):
    def __init__(
        self,
        config: NotteEnvConfig | None = None,
        browser: BrowserDriver | None = None,
        pool: BrowserPool | None = None,
        llmserve: LLMService | None = None,
    ) -> None:
        if config is not None:
            if config.verbose:
                logger.info(f"🔧 Custom notte-env config: \n{config.model_dump_json(indent=2)}")
        self.config: NotteEnvConfig = config or NotteEnvConfig().use_llm()
        if llmserve is None:
            llmserve = LLMService(base_model=self.config.perception_model)
        self._browser: BrowserDriver = browser or BrowserDriver(pool=pool, config=self.config.browser)
        super().__init__(self._browser)
        self.controller: BrowserController = BrowserController(self._browser, verbose=self.config.verbose)

        self.trajectory: list[TrajectoryStep] = []
        self._context: ProcessedBrowserSnapshot | None = None
        self._action_space_pipe: MainActionSpacePipe = MainActionSpacePipe(llmserve=llmserve, config=self.config.action)
        self._data_scraping_pipe: DataScrapingPipe = DataScrapingPipe(
            llmserve=llmserve, browser=self._browser, config=self.config.scraping
        )
        self._node_resolution_pipe: NodeResolutionPipe = NodeResolutionPipe(
            browser=self._browser, type=self.config.preprocessing.type, verbose=self.config.verbose
        )

    @property
    def context(self) -> ProcessedBrowserSnapshot:
        if self._context is None:
            raise NoContextObservedError()
        return self._context

    @property
    def previous_actions(self) -> Sequence[BaseAction] | None:
        # This function is always called after trajectory.append(preobs)
        # —This means trajectory[-1] is always the "current (pre)observation"
        # And trajectory[-2] is the "previous observation" we're interested in.
        if len(self.trajectory) <= 1:
            return None
        previous_obs: Observation = self.trajectory[-2].obs
        if not previous_obs.has_space():
            return None  # we don't have a space for pre-observations
        if self.obs.clean_url != previous_obs.clean_url:
            return None  # the page has significantly changed
        if previous_obs.space is None:
            raise InvalidInternalCheckError(
                check="Previous observation has no space. This should never happen.",
                url=previous_obs.metadata.url,
                dev_advice=(
                    "This technnically should never happen. There is likely an issue during the action space pipe."
                ),
            )
        return previous_obs.space.actions("all")

    @property
    def obs(self) -> Observation:
        if len(self.trajectory) <= 0:
            raise NoContextObservedError()
        return self.trajectory[-1].obs

    def progress(self) -> TrajectoryProgress:
        return TrajectoryProgress(
            max_steps=self.config.max_steps,
            current_step=len(self.trajectory),
        )

    # ---------------------------- observe, step functions ----------------------------

    def _preobserve(self, snapshot: BrowserSnapshot, action: BaseAction) -> Observation:
        if len(self.trajectory) >= self.config.max_steps:
            raise MaxStepsReachedError(max_steps=self.config.max_steps)
        self._context = ProcessedSnapshotPipe.forward(snapshot, self.config.preprocessing)
        preobs = Observation.from_snapshot(snapshot, progress=self.progress())
        self.trajectory.append(TrajectoryStep(obs=preobs, action=action))
        return preobs

    async def _observe(
        self,
        pagination: PaginationParams,
        retry: int,
    ) -> Observation:
        if self.config.verbose:
            logger.info(f"🧿 observing page {self.context.snapshot.metadata.url}")
        self.obs.space = self._action_space_pipe.forward(
            self.context,
            self.previous_actions,
            pagination=pagination,
        )
        # TODO: improve this
        # Check if the snapshot has changed since the beginning of the trajectory
        # if it has, it means that the page was not fully loaded and that we should restart the oblisting
        time_diff = dt.datetime.now() - self.context.snapshot.metadata.timestamp
        if time_diff.total_seconds() > self.config.nb_seconds_between_snapshots_check:
            if self.config.verbose:
                logger.warning(
                    (
                        f"{time_diff.total_seconds()} seconds since the beginning of the action listing."
                        "Check if page content has changed..."
                    )
                )
            check_snapshot = await self._browser.snapshot(screenshot=False)
            if not self.context.snapshot.compare_with(check_snapshot) and retry > 0:
                if self.config.verbose:
                    logger.warning(
                        "Snapshot changed since the beginning of the action listing, retrying to observe again"
                    )
                _ = self._preobserve(check_snapshot, action=WaitAction(time_ms=int(time_diff.total_seconds() * 1000)))
                return await self._observe(retry=retry - 1, pagination=pagination)

        if (
            self.config.auto_scrape
            and self.obs.space.category is not None
            and self.obs.space.category.is_data()
            and not self.obs.has_data()
        ):
            if self.config.verbose:
                logger.info(f"🛺 Autoscrape enabled and page is {self.obs.space.category}. Scraping page...")
            self.obs.data = await self._data_scraping_pipe.forward(self.context, ScrapeParams())
        return self.obs

    @timeit("goto")
    async def goto(self, url: str | None) -> Observation:
        snapshot = await self._browser.goto(url)
        return self._preobserve(snapshot, action=GotoAction(url=snapshot.metadata.url))

    @timeit("observe")
    async def observe(
        self,
        url: str | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> Observation:
        _ = await self.goto(url)
        if self.config.verbose:
            logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
            logger.debug(f"ℹ️ context inodes IDs: {[node.id for node in self.context.interaction_nodes()]}")
        return await self._observe(
            pagination=PaginationParams.model_validate(pagination),
            retry=self.config.observe_max_retry_after_snapshot_update,
        )

    @timeit("execute")
    async def execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        if action_id == BrowserActionId.SCRAPE.value:
            # Scrape action is a special case
            return await self.scrape()
        exec_action = ExecutableAction.parse(action_id, params, enter=enter)
        action = await self._node_resolution_pipe.forward(exec_action, self._context)
        snapshot = await self.controller.execute(action)
        obs = self._preobserve(snapshot, action=action)
        return obs

    @timeit("act")
    async def act(
        self,
        action: BaseAction,
    ) -> Observation:
        if self.config.verbose:
            logger.info(f"🌌 starting execution of action {action.id}...")
        if isinstance(action, ScrapeAction):
            # Scrape action is a special case
            # TODO: think about flow. Right now, we do scraping and observation in one step
            return await self.god(instructions=action.instructions)
        action = await self._node_resolution_pipe.forward(action, self._context)
        snapshot = await self.controller.execute(action)
        if self.config.verbose:
            logger.info(f"🌌 action {action.id} executed in browser. Observing page...")
        _ = self._preobserve(snapshot, action=action)
        return await self._observe(
            pagination=PaginationParams(),
            retry=self.config.observe_max_retry_after_snapshot_update,
        )

    @timeit("step")
    async def step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> Observation:
        _ = await self.execute(action_id, params, enter=enter)
        if self.config.verbose:
            logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
            logger.debug(f"ℹ️ context inodes IDs: {[node.id for node in self.context.interaction_nodes()]}")
        return await self._observe(
            pagination=PaginationParams.model_validate(pagination),
            retry=self.config.observe_max_retry_after_snapshot_update,
        )

    @timeit("scrape")
    async def scrape(
        self,
        url: str | None = None,
        **scrape_params: Unpack[ScrapeParamsDict],
    ) -> Observation:
        if url is not None:
            _ = await self.goto(url)
        params = ScrapeParams(**scrape_params)
        self.obs.data = await self._data_scraping_pipe.forward(self.context, params)
        return self.obs

    @timeit("god")
    async def god(
        self,
        url: str | None = None,
        **params: Unpack[ScrapeAndObserveParamsDict],
    ) -> Observation:
        if self.config.verbose:
            logger.info("🌊 God mode activated (scraping + action listing)")
        if url is not None:
            _ = await self.goto(url)
        scrape = ScrapeParams.model_validate(params)
        pagination = PaginationParams.model_validate(params)
        space, data = await asyncio.gather(
            self._action_space_pipe.forward_async(
                self.context, previous_action_list=self.previous_actions, pagination=pagination
            ),
            self._data_scraping_pipe.forward_async(self.context, scrape),
        )
        self.obs.space = space
        self.obs.data = data
        return self.obs

    @timeit("reset")
    async def reset(self) -> None:
        if self.config.verbose:
            logger.info("🌊 Resetting environment...")
        self.trajectory = []
        self._context = None
        return await self._browser.reset()

    # ------------------------------ Private ---------------------------------------
