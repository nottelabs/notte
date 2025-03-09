import asyncio
import datetime as dt
from collections.abc import Sequence
from typing import Self, Unpack

from loguru import logger
from pydantic import BaseModel
from typing_extensions import override

from notte.actions.base import ExecutableAction
from notte.browser.observation import Observation, TrajectoryProgress
from notte.browser.pool.base import BaseBrowserPool
from notte.browser.snapshot import BrowserSnapshot
from notte.browser.window import BrowserWindow, BrowserWindowConfig
from notte.common.config import FrozenConfig
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
from notte.errors.env import MaxStepsReachedError, NoSnapshotObservedError
from notte.errors.processing import InvalidInternalCheckError
from notte.llms.engine import LlmModel
from notte.llms.service import LLMService
from notte.pipe.action.pipe import (
    MainActionSpaceConfig,
    MainActionSpacePipe,
)
from notte.pipe.preprocessing.pipe import (
    PreprocessingConfig,
    ProcessedSnapshotPipe,
)
from notte.pipe.resolution.pipe import NodeResolutionPipe
from notte.pipe.scraping.pipe import DataScrapingPipe, ScrapingConfig
from notte.sdk.types import (
    DEFAULT_MAX_NB_STEPS,
    PaginationParams,
    PaginationParamsDict,
    ScrapeParams,
    ScrapeParamsDict,
)


class ScrapeAndObserveParamsDict(ScrapeParamsDict, PaginationParamsDict):
    pass


class NotteEnvConfig(FrozenConfig):
    max_steps: int = DEFAULT_MAX_NB_STEPS
    preprocessing: PreprocessingConfig = PreprocessingConfig()
    window: BrowserWindowConfig = BrowserWindowConfig()
    scraping: ScrapingConfig = ScrapingConfig()
    action: MainActionSpaceConfig = MainActionSpaceConfig()
    observe_max_retry_after_snapshot_update: int = 2
    nb_seconds_between_snapshots_check: int = 10
    auto_scrape: bool = True
    perception_model: str | None = None
    verbose: bool = False
    structured_output_retries: int = 3

    def dev_mode(self: Self) -> Self:
        return self.set_deep_verbose()

    def user_mode(self: Self) -> Self:
        return self._copy_and_validate(
            verbose=True,
            window=self.window.set_verbose(),
            action=self.action.set_verbose(),
        )

    def groq(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.groq)

    def openai(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.openai)

    def cerebras(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.cerebras)

    def gemini(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.gemini)

    def model(self: Self, model: str) -> Self:
        return self._copy_and_validate(perception_model=model)

    def a11y(self: Self) -> Self:
        return self._copy_and_validate(preprocessing=self.preprocessing.accessibility())

    def dom(self: Self) -> Self:
        return self._copy_and_validate(preprocessing=self.preprocessing.dom())

    def steps(self: Self, max_steps: int | None = None) -> Self:
        return self._copy_and_validate(max_steps=max_steps if max_steps is not None else DEFAULT_MAX_NB_STEPS)

    def headless(self: Self, value: bool = True) -> Self:
        return self._copy_and_validate(window=self.window.set_headless(value))

    def not_headless(self: Self) -> Self:
        return self.headless(False)

    def cdp(self: Self, url: str) -> Self:
        return self._copy_and_validate(window=self.window.cdp(url))

    def llm_action_tagging(self: Self) -> Self:
        return self._copy_and_validate(action=self.action.set_llm_tagging())

    def llm_data_extract(self: Self) -> Self:
        return self._copy_and_validate(scraping=self.scraping.llm_extract())

    def web_security(self: Self, value: bool = True) -> Self:
        """
        Enable or disable web security.
        """
        return self._copy_and_validate(window=self.window.set_web_security(value))

    def disable_web_security(self: Self) -> Self:
        return self.web_security(False)

    def enable_web_security(self: Self) -> Self:
        return self.web_security(True)

    def disable_auto_scrape(self: Self) -> Self:
        return self._copy_and_validate(auto_scrape=False)

    def enable_auto_scrape(self: Self) -> Self:
        return self._copy_and_validate(auto_scrape=True)

    def use_llm(self: Self) -> Self:
        return self._copy_and_validate(
            action=self.action.set_llm_tagging(),
            scraping=self.scraping.llm_extract(),
        )

    def disable_perception(self: Self) -> Self:
        return self._copy_and_validate(perception_model=None)

    def set_structured_output_retries(self: Self, value: int) -> Self:
        return self._copy_and_validate(structured_output_retries=value)

    # New methods to replace properties
    def set_max_steps(self: Self, value: int) -> Self:
        return self._copy_and_validate(max_steps=value)

    def set_preprocessing(self: Self, value: PreprocessingConfig) -> Self:
        return self._copy_and_validate(preprocessing=value)

    def set_window(self: Self, value: BrowserWindowConfig) -> Self:
        return self._copy_and_validate(window=value)

    def set_scraping(self: Self, value: ScrapingConfig) -> Self:
        return self._copy_and_validate(scraping=value)

    def set_action(self: Self, value: MainActionSpaceConfig) -> Self:
        return self._copy_and_validate(action=value)

    def set_observe_max_retry_after_snapshot_update(self: Self, value: int) -> Self:
        return self._copy_and_validate(observe_max_retry_after_snapshot_update=value)

    def set_nb_seconds_between_snapshots_check(self: Self, value: int) -> Self:
        return self._copy_and_validate(nb_seconds_between_snapshots_check=value)

    def set_auto_scrape(self: Self, value: bool) -> Self:
        return self._copy_and_validate(auto_scrape=value)

    def set_perception_model(self: Self, value: str | None) -> Self:
        return self._copy_and_validate(perception_model=value)


class TrajectoryStep(BaseModel):
    obs: Observation
    action: BaseAction


class NotteEnv(AsyncResource):
    def __init__(
        self,
        config: NotteEnvConfig | None = None,
        window: BrowserWindow | None = None,
        pool: BaseBrowserPool | None = None,
        llmserve: LLMService | None = None,
    ) -> None:
        if config is not None:
            if config.verbose:
                logger.info(f"🔧 Custom notte-env config: \n{config.model_dump_json(indent=2)}")
        self.config: NotteEnvConfig = config or NotteEnvConfig().use_llm()
        if llmserve is None:
            llmserve = LLMService(
                base_model=self.config.perception_model, structured_output_retries=self.config.structured_output_retries
            )
        self._window: BrowserWindow = window or BrowserWindow(pool=pool, config=self.config.window)
        super().__init__(self._window)
        self.controller: BrowserController = BrowserController(self._window, verbose=self.config.verbose)

        self.trajectory: list[TrajectoryStep] = []
        self._snapshot: BrowserSnapshot | None = None
        self._action_space_pipe: MainActionSpacePipe = MainActionSpacePipe(llmserve=llmserve, config=self.config.action)
        self._data_scraping_pipe: DataScrapingPipe = DataScrapingPipe(
            llmserve=llmserve, window=self._window, config=self.config.scraping
        )
        self._node_resolution_pipe: NodeResolutionPipe = NodeResolutionPipe(
            window=self._window, type=self.config.preprocessing.type, verbose=self.config.verbose
        )

    @property
    def snapshot(self) -> BrowserSnapshot:
        if self._snapshot is None:
            raise NoSnapshotObservedError()
        return self._snapshot

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
            raise NoSnapshotObservedError()
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
        self._snapshot = ProcessedSnapshotPipe.forward(snapshot, self.config.preprocessing)
        preobs = Observation.from_snapshot(snapshot, progress=self.progress())
        self.trajectory.append(TrajectoryStep(obs=preobs, action=action))
        return preobs

    async def _observe(
        self,
        pagination: PaginationParams,
        retry: int,
    ) -> Observation:
        if self.config.verbose:
            logger.info(f"🧿 observing page {self.snapshot.metadata.url}")
        self.obs.space = self._action_space_pipe.forward(
            self.snapshot,
            self.previous_actions,
            pagination=pagination,
        )
        # TODO: improve this
        # Check if the snapshot has changed since the beginning of the trajectory
        # if it has, it means that the page was not fully loaded and that we should restart the oblisting
        time_diff = dt.datetime.now() - self.snapshot.metadata.timestamp
        if time_diff.total_seconds() > self.config.nb_seconds_between_snapshots_check:
            if self.config.verbose:
                logger.warning(
                    (
                        f"{time_diff.total_seconds()} seconds since the beginning of the action listing."
                        "Check if page content has changed..."
                    )
                )
            check_snapshot = await self._window.snapshot(screenshot=False)
            if not self.snapshot.compare_with(check_snapshot) and retry > 0:
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
            self.obs.data = await self._data_scraping_pipe.forward(self.snapshot, ScrapeParams())
        return self.obs

    @timeit("goto")
    async def goto(self, url: str | None) -> Observation:
        snapshot = await self._window.goto(url)
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
            logger.debug(f"ℹ️ snapshot inodes IDs: {[node.id for node in self.snapshot.interaction_nodes()]}")
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
        action = await self._node_resolution_pipe.forward(exec_action, self._snapshot)
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
        action = await self._node_resolution_pipe.forward(action, self._snapshot)
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
            logger.debug(f"ℹ️ snapshot inodes IDs: {[node.id for node in self.snapshot.interaction_nodes()]}")
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
        self.obs.data = await self._data_scraping_pipe.forward(self.snapshot, params)
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
                self.snapshot, previous_action_list=self.previous_actions, pagination=pagination
            ),
            self._data_scraping_pipe.forward_async(self.snapshot, scrape),
        )
        self.obs.space = space
        self.obs.data = data
        return self.obs

    @timeit("reset")
    @override
    async def reset(self) -> None:
        if self.config.verbose:
            logger.info("🌊 Resetting environment...")
        self.trajectory = []
        self._snapshot = None
        # reset the window
        await super().reset()
