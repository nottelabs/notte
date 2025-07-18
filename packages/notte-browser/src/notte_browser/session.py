import asyncio
import datetime as dt
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar, Unpack

from loguru import logger
from notte_core import enable_nest_asyncio
from notte_core.actions import (
    BaseAction,
    GotoAction,
    InteractionAction,
    # ReadFileAction,
    ScrapeAction,
    ToolAction,
)
from notte_core.browser.observation import Observation, StepResult
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import RaiseCondition, ScreenshotType, config
from notte_core.common.logging import timeit
from notte_core.common.resource import AsyncResource, SyncResource
from notte_core.common.telemetry import track_usage
from notte_core.data.space import DataSpace
from notte_core.errors.base import NotteBaseError
from notte_core.errors.provider import RateLimitError
from notte_core.llms.service import LLMService
from notte_core.profiling import profiler
from notte_core.space import ActionSpace
from notte_core.storage import BaseStorage
from notte_core.utils.webp_replay import ScreenshotReplay, WebpReplay
from notte_sdk.types import (
    Cookie,
    PaginationParams,
    PaginationParamsDict,
    ScrapeParams,
    ScrapeParamsDict,
    SessionStartRequest,
    SessionStartRequestDict,
    StepRequest,
    StepRequestDict,
)
from patchright.async_api import Locator
from pydantic import BaseModel, ValidationError
from typing_extensions import override

from notte_browser.action_selection.pipe import ActionSelectionPipe
from notte_browser.captcha import CaptchaHandler
from notte_browser.controller import BrowserController
from notte_browser.dom.locate import locate_element
from notte_browser.errors import (
    BrowserNotStartedError,
    CaptchaSolverNotAvailableError,
    NoActionObservedError,
    NoSnapshotObservedError,
    NoStorageObjectProvidedError,
    NoToolProvidedError,
)
from notte_browser.playwright import PlaywrightManager
from notte_browser.resolution import NodeResolutionPipe
from notte_browser.scraping.pipe import DataScrapingPipe
from notte_browser.tagging.action.pipe import MainActionSpacePipe
from notte_browser.tools.base import BaseTool
from notte_browser.window import BrowserWindow, BrowserWindowOptions

enable_nest_asyncio()


class SessionTrajectoryStep(BaseModel):
    action: BaseAction
    obs: Observation
    result: StepResult


class NotteSession(AsyncResource, SyncResource):
    observe_max_retry_after_snapshot_update: ClassVar[int] = 2
    nb_seconds_between_snapshots_check: ClassVar[int] = 10

    @track_usage("local.session.create")
    def __init__(
        self,
        enable_perception: bool = config.enable_perception,
        window: BrowserWindow | None = None,
        storage: BaseStorage | None = None,
        tools: list[BaseTool] | None = None,
        act_callback: Callable[[SessionTrajectoryStep], None] | None = None,
        **data: Unpack[SessionStartRequestDict],
    ) -> None:
        self._request: SessionStartRequest = SessionStartRequest.model_validate(data)
        if self._request.solve_captchas and not CaptchaHandler.is_available:
            raise CaptchaSolverNotAvailableError()
        self._enable_perception: bool = enable_perception
        self._window: BrowserWindow | None = window
        self.controller: BrowserController = BrowserController(verbose=config.verbose, storage=storage)
        self.storage: BaseStorage | None = storage
        llmserve = LLMService.from_config()
        self._action_space_pipe: MainActionSpacePipe = MainActionSpacePipe(llmserve=llmserve)
        self._data_scraping_pipe: DataScrapingPipe = DataScrapingPipe(llmserve=llmserve, type=config.scraping_type)
        self._action_selection_pipe: ActionSelectionPipe = ActionSelectionPipe(llmserve=llmserve)
        self.tools: list[BaseTool] = tools or []

        self.trajectory: list[SessionTrajectoryStep] = []
        self._snapshot: BrowserSnapshot | None = None
        self._action: BaseAction | None = None
        self._action_result: StepResult | None = None

        self.act_callback: Callable[[SessionTrajectoryStep], None] | None = act_callback

    async def aset_cookies(self, cookies: list[Cookie] | None = None, cookie_file: str | Path | None = None) -> None:
        await self.window.set_cookies(cookies=cookies, cookie_path=cookie_file)

    async def aget_cookies(self) -> list[Cookie]:
        return await self.window.get_cookies()

    @track_usage("local.session.cookies.set")
    def set_cookies(self, cookies: list[Cookie] | None = None, cookie_file: str | Path | None = None) -> None:
        _ = asyncio.run(self.aset_cookies(cookies=cookies, cookie_file=cookie_file))

    @track_usage("local.session.cookies.get")
    def get_cookies(self) -> list[Cookie]:
        return asyncio.run(self.aget_cookies())

    @override
    async def astart(self) -> None:
        if self._window is not None:
            return
        manager = PlaywrightManager()
        options = BrowserWindowOptions.from_request(self._request)
        self._window = await manager.new_window(options)

    @override
    async def astop(self) -> None:
        await self.window.close()
        self._window = None

    @override
    def start(self) -> None:
        _ = asyncio.run(self.astart())

    @override
    def stop(self) -> None:
        _ = asyncio.run(self.astop())

    @property
    def window(self) -> BrowserWindow:
        if self._window is None:
            raise BrowserNotStartedError()
        return self._window

    @property
    @track_usage("local.session.snapshot")
    def snapshot(self) -> BrowserSnapshot:
        if self._snapshot is None:
            raise NoSnapshotObservedError()
        return self._snapshot

    @property
    def previous_interaction_actions(self) -> Sequence[InteractionAction] | None:
        # This function is always called after trajectory.append(preobs)
        # —This means trajectory[-1] is always the "current (pre)observation"
        # And trajectory[-2] is the "previous observation" we're interested in.
        if len(self.trajectory) <= 0:
            return None
        if self.snapshot.clean_url != self.last_step.obs.clean_url:
            return None  # the page has significantly changed
        actions = self.last_step.obs.space.interaction_actions
        if len(actions) == 0:
            return None
        return actions

    @property
    def last_step(self) -> SessionTrajectoryStep:
        if len(self.trajectory) <= 0:
            raise NoSnapshotObservedError()
        return self.trajectory[-1]

    @track_usage("local.session.replay")
    def replay(self, screenshot_type: ScreenshotType = config.screenshot_type) -> WebpReplay:
        screenshots: list[bytes] = [step.obs.screenshot.bytes(screenshot_type) for step in self.trajectory]
        if len(screenshots) == 0:
            raise ValueError("No screenshots found in agent trajectory")
        return ScreenshotReplay.from_bytes(screenshots).get()

    # ---------------------------- observe, step functions ----------------------------

    async def _interaction_action_listing(
        self,
        pagination: PaginationParams,
        retry: int = observe_max_retry_after_snapshot_update,
    ) -> ActionSpace:
        if config.verbose:
            logger.info(f"🧿 observing page {self.snapshot.metadata.url}")
        space = await self._action_space_pipe.with_perception(enable_perception=self._enable_perception).forward(
            snapshot=self.snapshot,
            previous_action_list=self.previous_interaction_actions,
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
                self._snapshot = check_snapshot
                return await self._interaction_action_listing(retry=retry - 1, pagination=pagination)

        return space

    @timeit("observe")
    @track_usage("local.session.observe")
    @profiler.profiled()
    async def aobserve(
        self,
        url: str | None = None,
        instructions: str | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> Observation:
        # --------------------------------
        # ---------- Step 0: goto --------
        # --------------------------------

        if url is not None:
            _ = await self.astep(GotoAction(url=url))

        # --------------------------------
        # ------ Step 1: snapshot --------
        # --------------------------------

        # trigger exception at the begining of observe if no action is available
        if self._action is None or self._action_result is None:
            raise NoActionObservedError()
        last_action = self._action
        last_action_result = self._action_result

        self._snapshot = await self.window.snapshot()
        if config.verbose:
            logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_interaction_actions or []]}")
            logger.debug(f"ℹ️ snapshot inodes IDs: {[node.id for node in self.snapshot.interaction_nodes()]}")

        # --------------------------------
        # ---- Step 2: action listing ----
        # --------------------------------

        space = await self._interaction_action_listing(
            pagination=PaginationParams.model_validate(pagination),
            retry=self.observe_max_retry_after_snapshot_update,
        )
        if instructions is not None:
            obs = Observation.from_snapshot(self._snapshot, space=space)
            selected_actions = await self._action_selection_pipe.forward(obs, instructions=instructions)
            if not selected_actions.success:
                logger.warning(f"❌ Action selection failed: {selected_actions.reason}. Space will be empty.")
                space = ActionSpace.empty(description=f"Action selection failed: {selected_actions.reason}")
            else:
                space = space.filter([a.action_id for a in selected_actions.actions])

        # --------------------------------
        # ------- Step 3: tracing --------
        # --------------------------------

        obs = Observation.from_snapshot(self._snapshot, space=space)
        # final step is to add obs, action pair to the trajectory and trigger the callback
        if isinstance(self._action, InteractionAction) and len(self.trajectory) > 0:
            # this is usefull if screenshot_type = "last_action"
            self.last_step.obs.screenshot.last_action_id = self._action.id
        self.trajectory.append(SessionTrajectoryStep(obs=obs, action=last_action, result=last_action_result))
        if self.act_callback is not None:
            self.act_callback(self.trajectory[-1])
        return obs

    def observe(
        self, url: str | None = None, instructions: str | None = None, **pagination: Unpack[PaginationParamsDict]
    ) -> Observation:
        return asyncio.run(self.aobserve(url=url, instructions=instructions, **pagination))

    async def locate(self, action: BaseAction) -> Locator | None:
        action_with_selector = NodeResolutionPipe.forward(action, self._snapshot, verbose=config.verbose)
        if not isinstance(action_with_selector, InteractionAction) or action_with_selector.selector is None:
            return None
        locator: Locator = await locate_element(self.window.page, action_with_selector.selector)
        return locator

    @timeit("step")
    @track_usage("local.session.step")
    @profiler.profiled()
    async def astep(self, action: BaseAction | None = None, **data: Unpack[StepRequestDict]) -> StepResult:  # pyright: ignore[reportGeneralTypeIssues]
        # --------------------------------
        # ---- Step 0: action parsing ----
        # --------------------------------

        if action:
            data["action"] = action
        if not isinstance(action, ToolAction):
            step_action = StepRequest.model_validate(data).action
            assert step_action is not None
        else:
            step_action = action

        message = None
        exception = None
        scraped_data = None

        try:
            # --------------------------------
            # --- Step 1: action resolution --
            # --------------------------------

            self._action = NodeResolutionPipe.forward(step_action, self._snapshot, verbose=config.verbose)
            if config.verbose:
                logger.info(f"🌌 starting execution of action '{self._action.type}' ...")
            # --------------------------------
            # ----- Step 2: execution -------
            # --------------------------------

            message = self._action.execution_message()
            exception: Exception | None = None

            match self._action:
                case ScrapeAction():
                    scraped_data = await self.ascrape(instructions=self._action.instructions)
                    success = True
                case ToolAction():
                    tool_found = False
                    success = False
                    for tool in self.tools:
                        tool_func = tool.get_tool(type(self._action))
                        if tool_func is not None:
                            tool_found = True
                            res = tool_func(self._action)
                            message = res.message
                            scraped_data = res.data
                            success = res.success
                            break
                    if not tool_found:
                        raise NoToolProvidedError(self._action)
                case _:
                    success = await self.controller.execute(self.window, self._action, self._snapshot)

        except (NoSnapshotObservedError, NoStorageObjectProvidedError, NoToolProvidedError) as e:
            # this should be handled by the caller
            raise e
        except RateLimitError as e:
            success = False
            message = "Rate limit reached. Waiting before retry."
            exception = e
        except NotteBaseError as e:
            # When raise_on_failure is True, we use the dev message to give more details to the user
            success = False
            message = e.agent_message
            exception = e
        except ValidationError as e:
            success = False
            message = (
                "JSON Schema Validation error: The output format is invalid. "
                f"Please ensure your response follows the expected schema. Details: {str(e)}"
            )
            exception = e
        # /!\ Never use this except block, it will catch all errors and not be able to raise them
        # If you want an error not to be propagated to the LLM Agent. Define a NotteBaseError with the agent_message field.
        # except Exception as e:

        # --------------------------------
        # ------- Step 3: tracing --------
        # --------------------------------
        if config.verbose and self._action is not None:
            if success:
                logger.info(f"🌌 action '{self._action.type}' executed in browser.")
            else:
                logger.error(f"❌ action '{self._action.type}' failed in browser with error: {message}")
        self._snapshot = None
        # check if exception should be raised immediately
        if exception is not None and config.raise_condition is RaiseCondition.IMMEDIATELY:
            raise exception

        self._action_result = StepResult(
            success=success,
            message=message,
            data=scraped_data,
            exception=exception,
        )
        return self._action_result

    def step(self, action: BaseAction | None = None, **data: Unpack[StepRequestDict]) -> StepResult:  # pyright: ignore[reportGeneralTypeIssues]
        return asyncio.run(self.astep(action, **data))  # pyright: ignore[reportUnknownArgumentType, reportCallIssue, reportUnknownVariableType]

    @timeit("scrape")
    @track_usage("local.session.scrape")
    @profiler.profiled()
    async def ascrape(
        self,
        url: str | None = None,
        **scrape_params: Unpack[ScrapeParamsDict],
    ) -> DataSpace:
        if url is not None:
            _ = await self.astep(GotoAction(url=url))
            self._snapshot = await self.window.snapshot()
        params = ScrapeParams(**scrape_params)
        return await self._data_scraping_pipe.forward(self.window, self.snapshot, params)

    def scrape(self, url: str | None = None, **scrape_params: Unpack[ScrapeParamsDict]) -> DataSpace:
        return asyncio.run(self.ascrape(url=url, **scrape_params))

    @timeit("reset")
    @track_usage("local.session.reset")
    @override
    async def areset(self) -> None:
        if config.verbose:
            logger.info("🌊 Resetting environment...")
        self.trajectory = []
        self._snapshot = None
        self._action = None
        # reset the window
        await super().areset()

    @override
    def reset(self) -> None:
        _ = asyncio.run(self.areset())

    def start_from(self, session: "NotteSession") -> None:
        if len(self.trajectory) > 0 or self._snapshot is not None:
            raise ValueError("Session already started")
        if self.act_callback is not None:
            raise ValueError("Session already has an act callback")
        self.trajectory = session.trajectory
        self._snapshot = session._snapshot
        self._action = session._action
        self.act_callback = session.act_callback
