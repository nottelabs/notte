from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, Literal, Unpack, overload

from litellm import BaseModel
from loguru import logger
from notte_core import enable_nest_asyncio
from notte_core.actions import (
    ActionList,
    BaseAction,
    InteractionAction,
    # ReadFileAction,
    ScrapeAction,
    ToolAction,
)
from notte_core.browser.observation import ExecutionResult, Observation, Screenshot
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import CookieDict, PerceptionType, RaiseCondition, ScreenshotType, config
from notte_core.common.logging import timeit
from notte_core.common.resource import AsyncResource, SyncResource
from notte_core.common.telemetry import track_usage
from notte_core.data.space import DataSpace, ImageData, StructuredData, TBaseModel
from notte_core.errors.actions import InvalidActionError
from notte_core.errors.base import NotteBaseError
from notte_core.errors.provider import RateLimitError
from notte_core.llms.service import LLMService
from notte_core.profiling import profiler
from notte_core.space import ActionSpace
from notte_core.storage import BaseStorage
from notte_core.trajectory import Trajectory
from notte_core.utils.files import create_or_append_cookies_to_file
from notte_core.utils.webp_replay import ScreenshotReplay, WebpReplay
from notte_sdk.types import (
    ExecutionRequest,
    ExecutionRequestDict,
    PaginationParams,
    PaginationParamsDict,
    ScrapeMarkdownParamsDict,
    ScrapeParams,
    ScrapeParamsDict,
    SessionStartRequest,
    SessionStartRequestDict,
)
from pydantic import RootModel, ValidationError
from typing_extensions import override

from notte_browser.action_selection.pipe import ActionSelectionPipe
from notte_browser.captcha import CaptchaHandler
from notte_browser.controller import BrowserController
from notte_browser.dom.locate import locate_element
from notte_browser.errors import (
    BrowserNotStartedError,
    CaptchaSolverNotAvailableError,
    EmptyPageContentError,
    NoSnapshotObservedError,
    NoStorageObjectProvidedError,
    NoToolProvidedError,
)
from notte_browser.playwright import PlaywrightManager
from notte_browser.playwright_async_api import Locator, Page
from notte_browser.resolution import NodeResolutionPipe
from notte_browser.scraping.pipe import DataScrapingPipe
from notte_browser.tagging.action.pipe import MainActionSpacePipe
from notte_browser.tools.base import BaseTool
from notte_browser.window import BrowserWindow, BrowserWindowOptions

enable_nest_asyncio()


# TODO: ACT callback
class NotteSession(AsyncResource, SyncResource):
    observe_max_retry_after_snapshot_update: ClassVar[int] = 2
    nb_seconds_between_snapshots_check: ClassVar[int] = 10

    @track_usage("local.session.create")
    def __init__(
        self,
        *,
        perception_type: PerceptionType = config.perception_type,
        raise_on_failure: bool = config.raise_on_session_execution_failure,
        cookie_file: str | Path | None = None,
        storage: BaseStorage | None = None,
        tools: list[BaseTool] | None = None,
        window: BrowserWindow | None = None,
        **data: Unpack[SessionStartRequestDict],
    ) -> None:
        self._request: SessionStartRequest = SessionStartRequest.model_validate(data)
        if self._request.solve_captchas and not CaptchaHandler.is_available:
            raise CaptchaSolverNotAvailableError()
        self.screenshot_type: ScreenshotType = self._request.screenshot_type
        self._window: BrowserWindow | None = window
        self.controller: BrowserController = BrowserController(verbose=config.verbose, storage=storage)
        self.storage: BaseStorage | None = storage
        llmserve = LLMService.from_config(perception_type=perception_type)
        self._action_space_pipe: MainActionSpacePipe = MainActionSpacePipe(llmserve=llmserve)
        self._data_scraping_pipe: DataScrapingPipe = DataScrapingPipe(llmserve=llmserve, type=config.scraping_type)
        self._action_selection_pipe: ActionSelectionPipe = ActionSelectionPipe(llmserve=llmserve)
        self.tools: list[BaseTool] = tools or []
        self.default_perception_type: PerceptionType = perception_type
        self.default_raise_on_failure: bool = raise_on_failure
        self.trajectory: Trajectory = Trajectory()
        self._snapshot: BrowserSnapshot | None = None
        self._cookie_file: Path | None = Path(cookie_file) if cookie_file is not None else None

    @track_usage("local.session.cookies.set")
    async def aset_cookies(
        self, cookies: list[CookieDict] | None = None, cookie_file: str | Path | None = None
    ) -> None:
        await self.window.set_cookies(cookies=cookies, cookie_path=cookie_file)

    @staticmethod
    def script(storage: BaseStorage | None = None, **data: Unpack[SessionStartRequestDict]) -> NotteSession:
        return NotteSession(storage=storage, raise_on_failure=True, perception_type="fast", **data)

    @track_usage("local.session.cookies.get")
    async def aget_cookies(self) -> list[CookieDict]:
        return await self.window.get_cookies()

    def set_cookies(self, cookies: list[CookieDict] | None = None, cookie_file: str | Path | None = None) -> None:
        _ = asyncio.run(self.aset_cookies(cookies=cookies, cookie_file=cookie_file))

    def get_cookies(self) -> list[CookieDict]:
        return asyncio.run(self.aget_cookies())

    @override
    @track_usage("local.session.start")
    async def astart(self) -> None:
        if self._window is not None:
            return
        manager = PlaywrightManager()
        options = BrowserWindowOptions.from_request(self._request)
        self._window = await manager.new_window(options)
        if self._cookie_file is not None:
            if Path(self._cookie_file).exists():
                logger.info(f"🍪 Automatically loading cookies from {self._cookie_file}")
                await self.aset_cookies(cookie_file=self._cookie_file)
            else:
                logger.warning(f"🍪 Cookie file {self._cookie_file} not found, skipping cookie loading")

    @override
    @track_usage("local.session.stop")
    async def astop(self) -> None:
        if self._cookie_file is not None:
            cookies = await self.aget_cookies()
            create_or_append_cookies_to_file(self._cookie_file, cookies)
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

    @snapshot.setter
    def snapshot(self, value: BrowserSnapshot | None) -> None:  # pyright: ignore [reportPropertyTypeMismatch]
        self._snapshot = value

    @property
    def page(self) -> Page:
        return self.window.page

    @property
    def previous_interaction_actions(self) -> Sequence[InteractionAction] | None:
        # This function is always called after trajectory.append(preobs)
        # —This means trajectory[-1] is always the "current (pre)observation"
        # And trajectory[-2] is the "previous observation" we're interested in.
        last_observation = self.trajectory.last_observation
        if last_observation is None or self.snapshot.clean_url != last_observation.clean_url:
            return None  # the page has significantly changed
        actions = last_observation.space.interaction_actions
        if len(actions) == 0:
            return None
        return actions

    @track_usage("local.session.replay")
    @profiler.profiled()
    def replay(self, screenshot_type: ScreenshotType | None = None) -> WebpReplay:
        screenshot_type = screenshot_type or self.screenshot_type

        screenshots_traj = list(self.trajectory.all_screenshots())
        screenshots: list[bytes] = [screen.bytes(screenshot_type) for screen in screenshots_traj]
        if len(screenshots) == 0:
            raise ValueError("No screenshots found in agent trajectory")
        elif len(screenshots) > 1 and screenshots[0] == Observation.empty().screenshot.bytes(screenshot_type):
            screenshots = screenshots[1:]
        return ScreenshotReplay.from_bytes(screenshots).get(quality=90)  # pyright: ignore [reportArgumentType]

    # ---------------------------- observe, step functions ----------------------------

    async def _interaction_action_listing(
        self,
        pagination: PaginationParams,
        perception_type: PerceptionType,
        retry: int = observe_max_retry_after_snapshot_update,
    ) -> ActionSpace:
        if config.verbose:
            logger.info(f"🧿 observing page {self.snapshot.metadata.url} and {perception_type} perception")
        space = await self._action_space_pipe.with_perception(perception_type=perception_type).forward(
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
                self.snapshot = check_snapshot
                return await self._interaction_action_listing(
                    perception_type=perception_type, retry=retry - 1, pagination=pagination
                )

        return space

    @track_usage("local.session.screenshot")
    async def ascreenshot(self) -> Screenshot:
        screenshot_bytes = await self.window.screenshot()
        screenshot = Screenshot(raw=screenshot_bytes, bboxes=[], last_action_id=None)
        await self.trajectory.append(screenshot)
        return screenshot

    def screenshot(
        self,
    ) -> Screenshot:
        return asyncio.run(self.ascreenshot())

    @timeit("observe")
    @track_usage("local.session.observe")
    @profiler.profiled()
    async def aobserve(
        self,
        instructions: str | None = None,
        perception_type: PerceptionType | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> Observation:
        # --------------------------------
        # ------ Step 1: snapshot --------
        # --------------------------------

        # ensure we're on a page
        is_page_default = self.window.page.url == "about:blank"

        if is_page_default:
            logger.info(
                "Session url is 'about:blank': returning empty observation. Perform goto action before observing to get a more meaningful observation."
            )
            obs = Observation.empty()
            await self.trajectory.append(obs)
            return obs

        self.snapshot = await self.window.snapshot()

        if config.verbose:
            logger.debug(f"ℹ️ previous actions IDs: {[a.id for a in self.previous_interaction_actions or []]}")
            logger.debug(f"ℹ️ snapshot inodes IDs: {[node.id for node in self.snapshot.interaction_nodes()]}")

        # --------------------------------
        # ---- Step 2: action listing ----
        # --------------------------------

        space = await self._interaction_action_listing(
            perception_type=perception_type or self.default_perception_type,
            pagination=PaginationParams.model_validate(pagination),
            retry=self.observe_max_retry_after_snapshot_update,
        )
        if instructions is not None:
            obs = Observation.from_snapshot(self.snapshot, space=space)
            selected_actions = await self._action_selection_pipe.forward(obs, instructions=instructions)
            if not selected_actions.success:
                logger.warning(f"❌ Action selection failed: {selected_actions.reason}. Space will be empty.")
                space = ActionSpace.empty(description=f"Action selection failed: {selected_actions.reason}")
            else:
                space = space.filter(action_ids=[a.action_id for a in selected_actions.actions])

        # --------------------------------
        # ------- Step 3: tracing --------
        # --------------------------------

        obs = Observation.from_snapshot(self.snapshot, space=space)

        await self.trajectory.append(obs)
        return obs

    def observe(
        self,
        instructions: str | None = None,
        perception_type: PerceptionType | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> Observation:
        return asyncio.run(self.aobserve(instructions=instructions, perception_type=perception_type, **pagination))

    async def locate(self, action: BaseAction) -> Locator | None:
        action_with_selector = NodeResolutionPipe.forward(action, self._snapshot)
        if isinstance(action_with_selector, InteractionAction) and action_with_selector.selector is not None:
            locator: Locator = await locate_element(self.window.page, action_with_selector.selector)
            assert isinstance(action_with_selector, InteractionAction) and action_with_selector.selector is not None
            return locator
        return None

    @overload
    async def aexecute(self, action: BaseAction, *, raise_on_failure: bool | None = None) -> ExecutionResult: ...
    @overload
    async def aexecute(self, action: dict[str, Any], *, raise_on_failure: bool | None = None) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self,
        action: None = None,
        *,
        raise_on_failure: bool | None = None,
        **data: Unpack[ExecutionRequestDict],
    ) -> ExecutionResult: ...

    @timeit("aexecute")
    @track_usage("local.session.execute")
    @profiler.profiled()
    async def aexecute(
        self,
        action: BaseAction | dict[str, Any] | None = None,
        *,
        raise_on_failure: bool | None = None,
        **data: Unpack[ExecutionRequestDict],
    ) -> ExecutionResult:
        """
        Execute an action, either by passing a BaseAction as the first argument, or by passing ExecutionRequestDict fields as kwargs.
        """
        step_action = ExecutionRequest.get_action(action=action, data=data)

        message = None
        exception = None
        scraped_data = None
        resolved_action = None

        try:
            # --------------------------------
            # --- Step 1: action resolution --
            # --------------------------------

            resolved_action = NodeResolutionPipe.forward(step_action, self._snapshot, verbose=config.verbose)
            if config.verbose:
                logger.info(f"🌌 starting execution of action '{resolved_action.type}' ...")
            # --------------------------------
            # ----- Step 2: execution -------
            # --------------------------------

            message = resolved_action.execution_message()
            exception: Exception | None = None

            match resolved_action:
                case ScrapeAction():
                    scraped_data = await self._ascrape(instructions=resolved_action.instructions)
                    success = True
                case ToolAction():
                    tool_found = False
                    success = False
                    for tool in self.tools:
                        tool_func = tool.get_tool(type(resolved_action))
                        if tool_func is not None:
                            tool_found = True
                            res = await tool_func(resolved_action)
                            message = res.message
                            scraped_data = res.data
                            success = res.success
                            break
                    if not tool_found:
                        raise NoToolProvidedError(resolved_action)
                case _:
                    success = await self.controller.execute(self.window, resolved_action, self._snapshot)

        except (NoSnapshotObservedError, NoStorageObjectProvidedError, NoToolProvidedError) as e:
            # this should be handled by the caller
            raise e
        except InvalidActionError as e:
            success = False
            message = e.dev_message
            exception = e
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
        if config.verbose and resolved_action is not None:
            if success:
                logger.info(f"🌌 action '{resolved_action.type}' executed in browser.")
            else:
                logger.error(f"❌ action '{resolved_action.type}' failed in browser with error: {message}")

        # check if exception should be raised immediately
        if exception is not None and config.raise_condition is RaiseCondition.IMMEDIATELY:
            raise exception

        if resolved_action is None:
            # keep the initial action in the trajectory
            if step_action is None:
                # this shouldnt happen
                raise InvalidActionError(reason="Could not resolve action", action_id="")
            else:
                resolved_action = step_action

        execution_result = ExecutionResult(
            action=resolved_action,
            success=success,
            message=message,
            data=scraped_data,
            exception=exception,
        )
        await self.trajectory.append(execution_result)

        # add screenshot to trajectory (after the execution)
        _ = await self.ascreenshot()

        _raise_on_failure = raise_on_failure if raise_on_failure is not None else self.default_raise_on_failure
        if _raise_on_failure and exception is not None:
            raise exception
        return execution_result

    def execute_saved_actions(self, actions_file: str) -> None:
        with open(actions_file, "r") as f:
            action_list = ActionList.model_validate_json(f.read())
        for i, action in enumerate(action_list.actions):
            logger.info(f"💡 Step {i + 1}/{len(action_list.actions)}: executing action '{action.type}' {action.id}")
            res = self.execute(action)
            logger.info(f"{'✅' if res.success else '❌'} - {res.message}")
            if not res.success:
                logger.error("🚨 Stopping execution of saved actions since last action failed...")
                return
            obs = self.observe(perception_type="fast")
            logger.info(f"🌌 Observation. Current URL: {obs.clean_url}")
        logger.info("🎉 All actions executed successfully")

    @overload
    def execute(self, /, action: BaseAction, *, raise_on_failure: bool | None = None) -> ExecutionResult: ...
    @overload
    def execute(self, /, action: dict[str, Any], *, raise_on_failure: bool | None = None) -> ExecutionResult: ...
    @overload
    def execute(
        self,
        *,
        action: None = None,
        raise_on_failure: bool | None = None,
        **data: Unpack[ExecutionRequestDict],
    ) -> ExecutionResult: ...

    def execute(
        self,
        action: BaseAction | dict[str, Any] | None = None,
        raise_on_failure: bool | None = None,
        **kwargs: Unpack[ExecutionRequestDict],
    ) -> ExecutionResult:
        """
        Synchronous version of aexecute, supporting both BaseAction and ExecutionRequestDict fields.
        """

        return asyncio.run(
            self.aexecute(action=action, raise_on_failure=raise_on_failure, **kwargs)  # pyright: ignore [reportArgumentType]
        )

    @overload
    async def ascrape(self, /, **params: Unpack[ScrapeMarkdownParamsDict]) -> str: ...

    @overload
    async def ascrape(
        self, *, instructions: str, **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> StructuredData[BaseModel]: ...

    @overload
    async def ascrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    @overload
    async def ascrape(self, /, *, only_images: Literal[True]) -> list[ImageData]: ...

    @timeit("scrape")
    @track_usage("local.session.scrape")
    async def ascrape(self, **params: Unpack[ScrapeParamsDict]) -> StructuredData[BaseModel] | str | list[ImageData]:
        data = await self._ascrape(**params)
        if data.images is not None:
            return data.images
        if data.structured is not None:
            if isinstance(data.structured.data, RootModel):
                # automatically unwrap the root model otherwise it makes it unclear for the user
                data.structured.data = data.structured.data.root  # pyright: ignore [reportUnknownMemberType, reportAttributeAccessIssue]
            return data.structured
        return data.markdown

    @profiler.profiled()
    async def _ascrape(self, retries: int = 3, wait_time: int = 2000, **params: Unpack[ScrapeParamsDict]) -> DataSpace:
        try:
            return await self._data_scraping_pipe.forward(
                window=self.window,
                snapshot=await self.window.snapshot(),
                params=ScrapeParams.model_validate(params),
            )
        except EmptyPageContentError as e:
            if retries == 0:
                raise e
            logger.warning(f"Scrape failed after empty page content, retrying in {wait_time / 1000} seconds...")
            await asyncio.sleep(wait_time / 1000)
            return await self._ascrape(retries=retries - 1, wait_time=wait_time, **params)
        except Exception as e:
            raise e

    @overload
    def scrape(self, /, **params: Unpack[ScrapeMarkdownParamsDict]) -> str: ...

    @overload
    def scrape(self, *, instructions: str, **params: Unpack[ScrapeMarkdownParamsDict]) -> StructuredData[BaseModel]: ...

    @overload
    def scrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    @overload
    def scrape(self, /, *, only_images: Literal[True]) -> list[ImageData]: ...  # pyright: ignore [reportOverlappingOverload]

    def scrape(self, **params: Unpack[ScrapeParamsDict]) -> StructuredData[BaseModel] | str | list[ImageData]:
        return asyncio.run(self.ascrape(**params))

    @timeit("reset")
    @track_usage("local.session.reset")
    @override
    async def areset(self) -> None:
        if config.verbose:
            logger.info("🌊 Resetting environment...")
        self.trajectory = Trajectory()
        self.snapshot = None
        # reset the window
        await super().areset()

    @override
    def reset(self) -> None:
        _ = asyncio.run(self.areset())

    def start_from(self, session: "NotteSession") -> None:
        if len(self.trajectory) > 0 or self._snapshot is not None:
            raise ValueError("Session already started")
        self.trajectory = session.trajectory
        self.snapshot = session._snapshot
