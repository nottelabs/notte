import asyncio
import datetime as dt
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar, Unpack

from loguru import logger
from notte_core.actions.base import ExecutableAction
from notte_core.browser.observation import Observation, TrajectoryProgress
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import config
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
from notte_core.llms.service import LLMService
from notte_core.utils.webp_replay import ScreenshotReplay, WebpReplay
from notte_sdk.types import (
    Cookie,
    PaginationParams,
    PaginationParamsDict,
    ScrapeParams,
    ScrapeParamsDict,
    SessionStartRequest,
    SessionStartRequestDict,
)
from pydantic import BaseModel
from typing_extensions import override

from notte_browser.controller import BrowserController
from notte_browser.errors import BrowserNotStartedError, MaxStepsReachedError, NoSnapshotObservedError
from notte_browser.playwright import GlobalWindowManager
from notte_browser.resolution import NodeResolutionPipe
from notte_browser.scraping.pipe import DataScrapingPipe
from notte_browser.tagging.action.pipe import MainActionSpacePipe
from notte_browser.window import BrowserWindow, BrowserWindowOptions


class ScrapeAndObserveParamsDict(ScrapeParamsDict, PaginationParamsDict):
    pass


class TrajectoryStep(BaseModel):
    obs: Observation
    action: BaseAction


class NotteSession(AsyncResource):
    observe_max_retry_after_snapshot_update: ClassVar[int] = 2
    nb_seconds_between_snapshots_check: ClassVar[int] = 10

    def __init__(
        self,
        headless: bool = True,
        window: BrowserWindow | None = None,
        act_callback: Callable[[BaseAction, Observation], None] | None = None,
        **data: Unpack[SessionStartRequestDict],
    ) -> None:
        llmserve = LLMService(base_model=config.perception_model or config.reasoning_model)
        self._request: SessionStartRequest = SessionStartRequest.model_validate(data)
        self._headless: bool = headless
        self._window: BrowserWindow | None = window
        self.controller: BrowserController = BrowserController(verbose=config.verbose)

        self.trajectory: list[TrajectoryStep] = []
        self._snapshot: BrowserSnapshot | None = None
        self._action_space_pipe: MainActionSpacePipe = MainActionSpacePipe(llmserve=llmserve)
        self._data_scraping_pipe: DataScrapingPipe = DataScrapingPipe(llmserve=llmserve, type=config.scraping_type)
        self.act_callback: Callable[[BaseAction, Observation], None] | None = act_callback

        # Track initialization
        capture_event(
            "page.initialized",
            {
                "config": {
                    "perception_model": config.perception_model,
                    "auto_scrape": config.auto_scrape,
                    "headless": self._headless,
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
        options = BrowserWindowOptions.from_request(self._request, headless=self._headless)
        self._window = await GlobalWindowManager.new_window(options)

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
            max_steps=self._request.max_steps,
            current_step=len(self.trajectory),
        )

    def replay(self) -> WebpReplay:
        screenshots: list[bytes] = [step.obs.screenshot for step in self.trajectory if step.obs.screenshot is not None]
        if len(screenshots) == 0:
            raise ValueError("No screenshots found in agent trajectory")
        return ScreenshotReplay.from_bytes(screenshots).get()

    # ---------------------------- observe, step functions ----------------------------

    def _preobserve(self, snapshot: BrowserSnapshot, action: BaseAction) -> Observation:
        if len(self.trajectory) >= self._request.max_steps:
            raise MaxStepsReachedError(max_steps=self._request.max_steps)
        self._snapshot = snapshot
        preobs = Observation.from_snapshot(snapshot, space=EmptyActionSpace(), progress=self.progress())
        self.trajectory.append(TrajectoryStep(obs=preobs, action=action))
        if self.act_callback is not None:
            self.act_callback(action, preobs)
        return preobs

    async def _observe(
        self,
        enable_perception: bool,
        pagination: PaginationParams,
        retry: int,
    ) -> Observation:
        if config.verbose:
            logger.info(f"🧿 observing page {self.snapshot.metadata.url}")
        self.obs.space = self._action_space_pipe.with_perception(enable_perception).forward(
            snapshot=self.snapshot,
            previous_action_list=self.previous_actions,
            pagination=pagination,
        )
        # TODO: improve this
        # Check if the snapshot has changed since the beginning of the trajectory
        # if it has, it means that the page was not fully loaded and that we should restart the oblisting
        time_diff = dt.datetime.now() - self.snapshot.metadata.timestamp
        if time_diff.total_seconds() > self.nb_seconds_between_snapshots_check:
            if config.verbose:
                logger.warning(
                    (
                        f"{time_diff.total_seconds()} seconds since the beginning of the action listing."
                        "Check if page content has changed..."
                    )
                )
            check_snapshot = await self.window.snapshot(screenshot=False)
            if not self.snapshot.compare_with(check_snapshot) and retry > 0:
                if config.verbose:
                    logger.warning(
                        "Snapshot changed since the beginning of the action listing, retrying to observe again"
                    )
                _ = self._preobserve(check_snapshot, action=WaitAction(time_ms=int(time_diff.total_seconds() * 1000)))
                return await self._observe(enable_perception=enable_perception, retry=retry - 1, pagination=pagination)

        if (
            config.auto_scrape
            and self.obs.space.category is not None
            and self.obs.space.category.is_data()
            and not self.obs.has_data()
        ):
            if config.verbose:
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
        enable_perception: bool = config.enable_perception,
        **pagination: Unpack[PaginationParamsDict],
    ) -> Observation:
        _ = await self.goto(url)
        if config.verbose:
            logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
            logger.debug(f"ℹ️ snapshot inodes IDs: {[node.id for node in self.snapshot.interaction_nodes()]}")
        return await self._observe(
            enable_perception=enable_perception,
            pagination=PaginationParams.model_validate(pagination),
            retry=self.observe_max_retry_after_snapshot_update,
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
        action = await NodeResolutionPipe.forward(exec_action, self._snapshot, verbose=config.verbose)
        snapshot = await self.controller.execute(self.window, action)
        obs = self._preobserve(snapshot, action=action)
        return obs

    @timeit("act")
    @track_usage("page.act")
    async def act(
        self,
        action: BaseAction,
        enable_perception: bool = config.enable_perception,
    ) -> Observation:
        if config.verbose:
            logger.info(f"🌌 starting execution of action {action.id}...")
        if isinstance(action, ScrapeAction):
            # Scrape action is a special case
            # TODO: think about flow. Right now, we do scraping and observation in one step
            return await self.god(instructions=action.instructions, use_llm=False)
        action = await NodeResolutionPipe.forward(action, self._snapshot, verbose=config.verbose)
        snapshot = await self.controller.execute(self.window, action)
        if config.verbose:
            logger.info(f"🌌 action {action.id} executed in browser. Observing page...")
        _ = self._preobserve(snapshot, action=action)
        return await self._observe(
            enable_perception=enable_perception,
            pagination=PaginationParams(),
            retry=self.observe_max_retry_after_snapshot_update,
        )

    @timeit("step")
    @track_usage("page.step")
    async def step(
        self,
        action_id: str,
        params: dict[str, str] | str | None = None,
        enter: bool | None = None,
        enable_perception: bool = config.enable_perception,
        **pagination: Unpack[PaginationParamsDict],
    ) -> Observation:
        _ = await self.execute(action_id, params, enter=enter)
        if config.verbose:
            logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_actions or []]}")
            logger.debug(f"ℹ️ snapshot inodes IDs: {[node.id for node in self.snapshot.interaction_nodes()]}")
        return await self._observe(
            enable_perception=enable_perception,
            pagination=PaginationParams.model_validate(pagination),
            retry=self.observe_max_retry_after_snapshot_update,
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
        if config.verbose:
            logger.info("🌊 God mode activated (scraping + action listing)")
        if url is not None:
            _ = await self.goto(url)
        scrape = ScrapeParams.model_validate(params)
        pagination = PaginationParams.model_validate(params)
        space, data = await asyncio.gather(
            self._action_space_pipe.with_perception(enable_perception=True).forward_async(
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
        if config.verbose:
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
