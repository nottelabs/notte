import asyncio
import datetime as dt
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Self, Unpack

from loguru import logger
from notte_core.actions.base import ExecutableAction
from notte_core.browser.allowlist import ActionAllowList, URLAllowList
from notte_core.browser.observation import Observation, TrajectoryProgress
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import FrozenConfig
from notte_core.common.logging import timeit
from notte_core.common.resource import AsyncResource
from notte_core.common.telemetry import capture_event, track_usage
from notte_core.controller.actions import (
    BaseAction,
    BrowserActionId,
    GotoAction,
    ScrapeAction,
    WaitAction,
)
from notte_core.controller.space import EmptyActionSpace
from notte_core.data.space import DataSpace
from notte_core.llms.engine import LlmModel
from notte_core.llms.service import LLMService
from notte_core.utils.webp_replay import ScreenshotReplay, WebpReplay
from notte_sdk.types import (
    DEFAULT_MAX_NB_STEPS,
    BrowserType,
    Cookie,
    PaginationParams,
    PaginationParamsDict,
    ProxySettings,
    ScrapeParams,
    ScrapeParamsDict,
)
from pydantic import BaseModel
from typing_extensions import override

from notte_browser.controller import BrowserController
from notte_browser.errors import BrowserNotStartedError, MaxStepsReachedError, NoSnapshotObservedError
from notte_browser.playwright import GlobalWindowManager
from notte_browser.resolution import NodeResolutionPipe
from notte_browser.scraping.pipe import DataScrapingPipe, ScrapingType
from notte_browser.tagging.action.pipe import (
    MainActionSpaceConfig,
    MainActionSpacePipe,
)
from notte_browser.window import BrowserWindow, BrowserWindowOptions


class ScrapeAndObserveParamsDict(ScrapeParamsDict, PaginationParamsDict):
    pass


class NotteSessionConfig(FrozenConfig):
    max_steps: int = DEFAULT_MAX_NB_STEPS
    window: BrowserWindowOptions = BrowserWindowOptions()
    action: MainActionSpaceConfig = MainActionSpaceConfig()
    observe_max_retry_after_snapshot_update: int = 2
    scraping_type: ScrapingType = ScrapingType.LLM_EXTRACT
    nb_seconds_between_snapshots_check: int = 10
    auto_scrape: bool = True
    perception_model: str = LlmModel.default()
    verbose: bool = False
    structured_output_retries: int = 3

    def dev_mode(self: Self) -> Self:
        format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        logger.configure(handlers=[dict(sink=sys.stderr, level="DEBUG", format=format)])  # type: ignore
        return self.set_deep_verbose()

    def user_mode(self: Self) -> Self:
        return self._copy_and_validate(
            verbose=True,
            window=self.window.set_verbose(),
            action=self.action.set_verbose(),
        )

    def agent_mode(self: Self) -> Self:
        format = "<level>{level: <8}</level> - <level>{message}</level>"
        logger.configure(handlers=[dict(sink=sys.stderr, level="INFO", format=format)])  # type: ignore
        return self.set_deep_verbose(False)

    def groq(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.groq)

    def openai(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.openai)

    def cerebras(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.cerebras)

    def gemini(self: Self) -> Self:
        return self._copy_and_validate(perception_model=LlmModel.gemini)

    def model(self: Self, model: LlmModel) -> Self:
        return self._copy_and_validate(perception_model=model)

    def set_allow_list(self: Self, allow_list: ActionAllowList) -> Self:
        return self._copy_and_validate(action=self.action.set_allow_list(allow_list))

    def set_url_allow_list(self, allow_list: URLAllowList) -> Self:
        return self._copy_and_validate(window=self.window.set_allow_list(allow_list))

    def set_max_steps(self: Self, max_steps: int | None = None) -> Self:
        return self._copy_and_validate(max_steps=max_steps if max_steps is not None else DEFAULT_MAX_NB_STEPS)

    def headless(self: Self, value: bool = True) -> Self:
        return self._copy_and_validate(window=self.window.set_headless(value))

    def set_proxy(self: Self, value: ProxySettings | None) -> Self:
        return self._copy_and_validate(window=self.window.set_proxy(value))

    def set_browser_type(self: Self, value: BrowserType) -> Self:
        return self._copy_and_validate(window=self.window.set_browser_type(value))

    def set_user_agent(self: Self, value: str | None) -> Self:
        return self._copy_and_validate(window=self.window.set_user_agent(value))

    def set_cdp_debug(self: Self, value: bool) -> Self:
        return self._copy_and_validate(window=self.window.set_cdp_debug(value))

    def not_headless(self: Self) -> Self:
        return self.headless(False)

    def cdp(self: Self, url: str) -> Self:
        return self._copy_and_validate(window=self.window.set_cdp_url(url))

    def llm_action_tagging(self: Self) -> Self:
        return self._copy_and_validate(action=self.action.set_llm_tagging())

    def set_llm_scraping(self: Self) -> Self:
        return self._copy_and_validate(scraping_type=ScrapingType.LLM_EXTRACT)

    def web_security(self: Self, value: bool = True) -> Self:
        """
        Enable or disable web security.
        """
        return self._copy_and_validate(window=self.window.set_web_security(value))

    def set_chrome_args(self: Self, value: list[str] | None) -> Self:
        return self._copy_and_validate(window=self.window.set_chrome_args(value))

    def disable_web_security(self: Self) -> Self:
        return self.web_security(False)

    def enable_web_security(self: Self) -> Self:
        return self.web_security(True)

    def disable_auto_scrape(self: Self) -> Self:
        return self.set_auto_scrape(False)

    def enable_auto_scrape(self: Self) -> Self:
        return self.set_auto_scrape(True)

    def use_llm(self: Self) -> Self:
        return self.set_llm_scraping().llm_action_tagging()

    def disable_perception(self: Self) -> Self:
        return self._copy_and_validate(
            scraping_type=ScrapingType.MARKDOWNIFY,
            action=self.action.set_simple(),
        ).disable_auto_scrape()

    def set_structured_output_retries(self: Self, value: int) -> Self:
        return self._copy_and_validate(structured_output_retries=value)

    def set_window(self: Self, value: BrowserWindowOptions) -> Self:
        return self._copy_and_validate(window=value)

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

    def steps(self: Self, value: int) -> Self:
        """
        Set the maximum number of steps for the agent.
        """
        return self.set_max_steps(value)

    def set_viewport(self: Self, width: int | None = None, height: int | None = None) -> Self:
        return self._copy_and_validate(window=self.window.set_viewport(width, height))


class TrajectoryStep(BaseModel):
    obs: Observation
    action: BaseAction


class NotteSession(AsyncResource):
    def __init__(
        self,
        config: NotteSessionConfig | None = None,
        window: BrowserWindow | None = None,
        llmserve: LLMService | None = None,
        act_callback: Callable[[BaseAction, Observation], None] | None = None,
    ) -> None:
        self.config: NotteSessionConfig = config or NotteSessionConfig().use_llm()
        if llmserve is None:
            llmserve = LLMService(
                base_model=self.config.perception_model,
                structured_output_retries=self.config.structured_output_retries,
            )
        self._window: BrowserWindow | None = window
        self.controller: BrowserController = BrowserController(verbose=self.config.verbose)

        self.trajectory: list[TrajectoryStep] = []
        self._snapshot: BrowserSnapshot | None = None
        self._action_space_pipe: MainActionSpacePipe = MainActionSpacePipe(llmserve=llmserve, config=self.config.action)
        self._data_scraping_pipe: DataScrapingPipe = DataScrapingPipe(llmserve=llmserve, type=self.config.scraping_type)
        self.act_callback: Callable[[BaseAction, Observation], None] | None = act_callback

        # Track initialization
        capture_event(
            "page.initialized",
            {
                "config": {
                    "perception_model": self.config.perception_model,
                    "auto_scrape": self.config.auto_scrape,
                    "headless": self.config.window.headless,
                }
            },
        )

    async def set_cookies(self, cookies: list[Cookie] | None = None, cookie_file: str | Path | None = None) -> None:
        await self.window.set_cookies(cookies=cookies, cookie_path=cookie_file)

    async def get_cookies(self) -> list[Cookie]:
        return await self.window.get_cookies()

    @override
    async def start(self) -> None:
        if self._window is not None:
            return
        self._window = await GlobalWindowManager.new_window(self.config.window)

    @override
    async def stop(self) -> None:
        await GlobalWindowManager.close_window(self.window)
        self._window = None

    @property
    def window(self) -> BrowserWindow:
        if self._window is None:
            raise BrowserNotStartedError()
        return self._window

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
        if self.obs.clean_url != previous_obs.clean_url:
            return None  # the page has significantly changed
        actions = previous_obs.space.actions("all")
        if len(actions) == 0:
            return None
        return actions

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

    def replay(self) -> WebpReplay:
        screenshots: list[bytes] = [step.obs.screenshot for step in self.trajectory if step.obs.screenshot is not None]
        if len(screenshots) == 0:
            raise ValueError("No screenshots found in agent trajectory")
        return ScreenshotReplay.from_bytes(screenshots).get()

    # ---------------------------- observe, step functions ----------------------------

    def _preobserve(self, snapshot: BrowserSnapshot, action: BaseAction) -> Observation:
        if len(self.trajectory) >= self.config.max_steps:
            raise MaxStepsReachedError(max_steps=self.config.max_steps)
        self._snapshot = snapshot
        preobs = Observation.from_snapshot(snapshot, space=EmptyActionSpace(), progress=self.progress())
        self.trajectory.append(TrajectoryStep(obs=preobs, action=action))
        if self.act_callback is not None:
            self.act_callback(action, preobs)
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
            check_snapshot = await self.window.snapshot(screenshot=False)
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
            self.obs.data = await self._data_scraping_pipe.forward(self.window, self.snapshot, ScrapeParams())
        return self.obs

    @timeit("goto")
    @track_usage("page.goto")
    async def goto(self, url: str | None) -> Observation:
        snapshot = await self.window.goto(url)
        return self._preobserve(snapshot, action=GotoAction(url=snapshot.metadata.url))

    @timeit("observe")
    @track_usage("page.observe")
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
    @track_usage("page.execute")
    async def execute(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
    ) -> Observation:
        if action_id == BrowserActionId.SCRAPE.value:
            # Scrape action is a special case
            self.obs.data = await self.scrape()
            return self.obs

        exec_action = ExecutableAction.parse(action_id, params, enter=enter)
        action = await NodeResolutionPipe.forward(exec_action, self._snapshot, verbose=self.config.verbose)
        snapshot = await self.controller.execute(self.window, action)
        obs = self._preobserve(snapshot, action=action)
        return obs

    @timeit("act")
    @track_usage("page.act")
    async def act(
        self,
        action: BaseAction,
    ) -> Observation:
        if self.config.verbose:
            logger.info(f"🌌 starting execution of action {action.id}...")
        if isinstance(action, ScrapeAction):
            # Scrape action is a special case
            # TODO: think about flow. Right now, we do scraping and observation in one step
            return await self.god(instructions=action.instructions, use_llm=False)
        action = await NodeResolutionPipe.forward(action, self._snapshot, verbose=self.config.verbose)
        snapshot = await self.controller.execute(self.window, action)
        if self.config.verbose:
            logger.info(f"🌌 action {action.id} executed in browser. Observing page...")
        _ = self._preobserve(snapshot, action=action)
        return await self._observe(
            pagination=PaginationParams(),
            retry=self.config.observe_max_retry_after_snapshot_update,
        )

    @timeit("step")
    @track_usage("page.step")
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
    @track_usage("page.scrape")
    async def scrape(
        self,
        url: str | None = None,
        **scrape_params: Unpack[ScrapeParamsDict],
    ) -> DataSpace:
        if url is not None:
            _ = await self.goto(url)
        params = ScrapeParams(**scrape_params)
        data = await self._data_scraping_pipe.forward(self.window, self.snapshot, params)
        self.obs.data = data
        return data

    @timeit("god")
    @track_usage("page.god")
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
                snapshot=self.snapshot,
                previous_action_list=self.previous_actions,
                pagination=pagination,
            ),
            self._data_scraping_pipe.forward_async(self.window, self.snapshot, scrape),
        )
        self.obs.space = space
        self.obs.data = data
        return self.obs

    @timeit("reset")
    @track_usage("page.reset")
    @override
    async def reset(self) -> None:
        if self.config.verbose:
            logger.info("🌊 Resetting environment...")
        self.trajectory = []
        self._snapshot = None
        # reset the window
        await super().reset()

    def start_from(self, session: "NotteSession") -> None:
        if len(self.trajectory) > 0 or self._snapshot is not None:
            raise ValueError("Session already started")
        if self.act_callback is not None:
            raise ValueError("Session already has an act callback")
        self.trajectory = session.trajectory
        self._snapshot = session._snapshot
        self.act_callback = session.act_callback
