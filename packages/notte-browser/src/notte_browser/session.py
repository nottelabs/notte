from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Unpack, overload

import requests
from notte_core import enable_nest_asyncio
from notte_core.actions import (
    BaseAction,
    EvaluateJsAction,
    FallbackFillAction,
    FillAction,
    FormFillAction,
    InteractionAction,
    MultiFactorFillAction,
    # ReadFileAction,
    ScrapeAction,
    SelectDropdownOptionAction,
    ToolAction,
)
from notte_core.actions.typedicts import (
    CaptchaSolveActionDict,
    CheckActionDict,
    ClickActionDict,
    CloseTabActionDict,
    DownloadFileActionDict,
    EvaluateJsActionDict,
    FallbackFillActionDict,
    FillActionDict,
    FormFillActionDict,
    GoBackActionDict,
    GoForwardActionDict,
    GotoActionDict,
    GotoNewTabActionDict,
    MultiFactorFillActionDict,
    PressKeyActionDict,
    ReloadActionDict,
    ScrollDownActionDict,
    ScrollUpActionDict,
    SelectDropdownOptionActionDict,
    SwitchTabActionDict,
    UploadFileActionDict,
    WaitActionDict,
    parse_action,
)
from notte_core.browser.observation import ExecutionResult, Observation, Screenshot, TimedSpan
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.common.config import BrowserBackend, CookieDict, RaiseCondition, config
from notte_core.common.logging import logger, timeit
from notte_core.common.resource import AsyncResource, SyncResource
from notte_core.common.telemetry import track_usage
from notte_core.credentials.base import BaseVault, LocatorAttributes
from notte_core.data.extraction import StructuredExtractor
from notte_core.data.fetch import FetchData, build_fetch_script, response_from_evaluated
from notte_core.data.space import DataSpace, StructuredData, TBaseModel
from notte_core.errors.actions import (
    ActionExecutionError,
    EvaluateJsNoDataError,
    EvaluateJsResultLimitError,
    InvalidActionError,
    VaultCredentialError,
)
from notte_core.errors.base import NotteBaseError
from notte_core.errors.provider import RateLimitError
from notte_core.profiling import profiler
from notte_core.storage import BaseStorage
from notte_core.trajectory import Trajectory
from notte_core.types import (
    LocalSessionStartRequest,
    LocalSessionStartRequestDict,
    PaginationParams,
    PaginationParamsDict,
    ScrapeMarkdownParamsDict,
    ScrapeParams,
    ScrapeParamsDict,
)
from notte_core.utils.files import create_or_append_cookies_to_file
from pydantic import BaseModel, RootModel, ValidationError
from typing_extensions import override

from notte_browser import execution
from notte_browser.action_space import build_action_space
from notte_browser.captcha import CaptchaHandler
from notte_browser.dom.locate import locate_element
from notte_browser.errors import (
    BrowserNotStartedError,
    CaptchaSolverNotAvailableError,
    InboxActionNotSupportedLocallyError,
    NoSnapshotObservedError,
    NoStorageObjectProvidedError,
    PlaywrightError,
    ScrapeFailedError,
    ScrapeIsNotAnActionError,
)
from notte_browser.evaluation_result import (
    PAGE_RESULT_GUARD,
    InvalidPagePayloadError,
    decode_page_result,
    format_evaluation_result,
    new_guard_token,
    page_expression,
    page_limit_reason,
)
from notte_browser.playwright import PlaywrightManager
from notte_browser.playwright_async_api import Locator, Page
from notte_browser.resolution import resolve_action
from notte_browser.scrape import default_extractor, scrape_page
from notte_browser.vault import VaultSecretsScreenshotMask
from notte_browser.window import BrowserWindow, BrowserWindowOptions

if TYPE_CHECKING:
    from notte_sdk.endpoints.personas import BasePersona

enable_nest_asyncio()


# TODO: ACT callback
class NotteSession(AsyncResource, SyncResource):
    @track_usage("local.session.create")
    def __init__(
        self,
        *,
        raise_on_failure: bool = config.raise_on_session_execution_failure,
        cookie_file: str | Path | None = None,
        storage: BaseStorage | None = None,
        vault: BaseVault | None = None,
        persona: BasePersona | None = None,
        window: BrowserWindow | None = None,
        keep_alive: bool = False,
        extractor: StructuredExtractor | None = None,
        **data: Unpack[LocalSessionStartRequestDict],
    ) -> None:
        if storage is not None and storage.is_remote:
            raise ValueError(
                "RemoteFileStorage is not supported for local sessions. Use a local storage implementation instead."
            )
        # CAPTCHA solving is a cloud SDK capability. Keep local sessions
        # runnable by default while preserving an explicit opt-in error.
        _ = data.setdefault("solve_captchas", False)
        self._request: LocalSessionStartRequest = LocalSessionStartRequest.model_validate(data)
        if self._request.solve_captchas and not CaptchaHandler.is_available:
            raise CaptchaSolverNotAvailableError()
        self._window: BrowserWindow | None = window
        self._verbose: bool = config.verbose
        self.storage: BaseStorage | None = storage
        # Structured scraping hands the page markdown to `extractor` (by default `notte_llm.LlmExtractor`, if installed).
        self._extractor: StructuredExtractor | None = extractor
        self._vault: BaseVault | None = None
        # Assigning through the `vault` property also masks the vault's secrets in screenshots.
        self.vault = vault
        if persona is not None:
            self.attach_persona(persona)
        else:
            self.persona: BasePersona | None = None
        self.default_raise_on_failure: bool = raise_on_failure
        self.trajectory: Trajectory = Trajectory()
        self._snapshot: BrowserSnapshot | None = None
        self._cookie_file: Path | None = Path(cookie_file) if cookie_file is not None else None
        self._keep_alive: bool = keep_alive
        self._keep_alive_msg: str = "🌌 Keep alive mode enabled, skipping session stop... Use `session.close()` to manually stop the session. Never `keep_alive=True` is production."

    def attach_persona(self, persona: BasePersona) -> None:
        """Use the persona's vault (if any) for credential placeholders. Read its inbox with `persona.emails()`."""
        self.persona = persona
        if self.vault is None and persona.has_vault:
            self.vault = persona.vault

    def set_vault(self, vault: BaseVault | None) -> None:
        self.vault = vault

    @property
    def vault(self) -> BaseVault | None:
        return self._vault

    @vault.setter
    def vault(self, vault: BaseVault | None) -> None:
        self._vault = vault
        self._sync_screenshot_mask()

    def _sync_screenshot_mask(self) -> None:
        """Mask the vault's secrets in every screenshot while a vault is attached.

        A custom mask set on the window by the caller is left untouched.
        """
        if self._window is None:
            return
        current = self._window.screenshot_mask
        if self._vault is not None:
            if current is None or isinstance(current, VaultSecretsScreenshotMask):
                self._window.screenshot_mask = VaultSecretsScreenshotMask(vault=self._vault)
        elif isinstance(current, VaultSecretsScreenshotMask):
            self._window.screenshot_mask = None

    @track_usage("local.session.cookies.set")
    async def aset_cookies(
        self, cookies: list[CookieDict] | None = None, cookie_file: str | Path | None = None
    ) -> None:
        await self.window.set_cookies(cookies=cookies, cookie_path=cookie_file)

    @staticmethod
    def script(storage: BaseStorage | None = None, **data: Unpack[LocalSessionStartRequestDict]) -> NotteSession:
        return NotteSession(storage=storage, raise_on_failure=True, **data)

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
        self._sync_screenshot_mask()
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
        if self._keep_alive:
            logger.info(self._keep_alive_msg)
            return
        await self.window.close()
        self._window = None

    @override
    def start(self) -> None:
        _ = asyncio.run(self.astart())

    @override
    def stop(self) -> None:
        if self._keep_alive:
            logger.info(self._keep_alive_msg)
            return
        _ = asyncio.run(self.astop())

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

    @snapshot.setter
    def snapshot(self, value: BrowserSnapshot | None) -> None:  # pyright: ignore [reportPropertyTypeMismatch]
        self._snapshot = value

    @property
    def page(self) -> Page:
        return self.window.page

    @property
    async def apage(self) -> Page:
        return self.window.page

    # ---------------------------- observe, step functions ----------------------------

    @track_usage("local.session.screenshot")
    async def ascreenshot(self) -> Screenshot:
        screenshot_bytes = await self.window.screenshot()
        screenshot = Screenshot(raw=screenshot_bytes)
        await self.trajectory.append(screenshot)
        return screenshot

    def screenshot(
        self,
    ) -> Screenshot:
        return asyncio.run(self.ascreenshot())

    @timeit("observe")
    @track_usage("local.session.observe")
    async def aobserve(self, **pagination: Unpack[PaginationParamsDict]) -> Observation:
        """Snapshot the page and list its interaction actions.

        The pagination parameters are kept for parity with the SDK's `observe`, but a local session
        always lists every action: they are validated and otherwise ignored.
        """
        # Profile with URL attribute
        async with profiler.profile("aobserve", service_name="observation") as span:
            if span is not None:
                span.set_attribute("url", self.window.page.url)

            return await self._aobserve_impl(**pagination)

    async def _aobserve_impl(self, **pagination: Unpack[PaginationParamsDict]) -> Observation:
        # --------------------------------
        # ------ Step 1: snapshot --------
        # --------------------------------

        with TimedSpan.capture() as span:
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
                logger.debug(f"ℹ️ snapshot inodes IDs: {[node.id for node in self.snapshot.interaction_nodes()]}")

            # --------------------------------
            # ---- Step 2: action listing ----
            # --------------------------------

            _ = PaginationParams.model_validate(pagination)
            if config.verbose:
                logger.info(f"🧿 observing page {self.snapshot.metadata.url}")
            space = build_action_space(self.snapshot.dom_node)

        # --------------------------------
        # ------- Step 3: tracing --------
        # --------------------------------

        obs = Observation.from_snapshot(self.snapshot, space=space, span=span.close())

        await self.trajectory.append(obs)
        return obs

    def observe(self, **pagination: Unpack[PaginationParamsDict]) -> Observation:
        return asyncio.run(self.aobserve(**pagination))

    async def locate(self, action: BaseAction) -> Locator | None:
        action_with_selector = await resolve_action(action, self._snapshot)
        if isinstance(action_with_selector, InteractionAction) and action_with_selector.selectors is not None:
            locator: Locator = await locate_element(self.window.page, action_with_selector.selectors)
            assert isinstance(action_with_selector, InteractionAction) and action_with_selector.selector is not None
            return locator
        return None

    async def _action_with_vault(self, action: BaseAction) -> BaseAction:
        # Only fill-type actions support credential replacement
        _SUPPORTED = (FormFillAction, FillAction, FallbackFillAction, MultiFactorFillAction, SelectDropdownOptionAction)
        if self.vault is None or not isinstance(action, _SUPPORTED) or not self.vault.contains_credentials(action):
            return action

        if self._window is not None:
            self.snapshot = await self.window.snapshot()
        snapshot = self.snapshot
        try:
            if isinstance(action, FormFillAction):
                attrs = LocatorAttributes(type=None, autocomplete=None, outerHTML=None)
                return await self.vault.replace_credentials(action, attrs, snapshot)

            locator = await self.locate(action)
            attrs = LocatorAttributes(type=None, autocomplete=None, outerHTML=None)
            if locator is not None:
                attrs = LocatorAttributes(
                    type=await locator.get_attribute("type"),
                    autocomplete=await locator.get_attribute("autocomplete"),
                    outerHTML=await locator.evaluate("el => el.outerHTML"),
                )
            return await self.vault.replace_credentials(action, attrs, snapshot)
        except ValueError as e:
            # Credential field not found in vault (e.g., vault has email but action needs username).
            # Fail the action: executing it as is would type the raw placeholder into the page.
            raise VaultCredentialError(str(e)) from e

    # BEGIN GENERATED OVERLOADS: aexecute (scripts/generate_action_overloads.py)
    @overload
    async def aexecute(self, action: BaseAction, *, raise_on_failure: bool | None = None) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[FormFillActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GotoActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GotoNewTabActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CloseTabActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[SwitchTabActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GoBackActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GoForwardActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ReloadActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[WaitActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[PressKeyActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ScrollUpActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ScrollDownActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CaptchaSolveActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[EvaluateJsActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ClickActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[FillActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[MultiFactorFillActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[FallbackFillActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CheckActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[SelectDropdownOptionActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[UploadFileActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def aexecute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[DownloadFileActionDict]
    ) -> ExecutionResult: ...

    # END GENERATED OVERLOADS: aexecute

    @timeit("aexecute")
    @track_usage("local.session.execute")
    async def aexecute(
        self,
        action: BaseAction | None = None,
        *,
        raise_on_failure: bool | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Execute an action, either by passing a BaseAction as the first argument, or by passing action fields as kwargs.
        """
        # Profile with action type attribute
        async with profiler.profile("aexecute", service_name="execution") as span:
            result = await self._aexecute_impl(action, raise_on_failure=raise_on_failure, **kwargs)
            if span is not None and result.action is not None:
                span.set_attribute("action_type", result.action.type)
            return result

    async def _aexecute_impl(
        self,
        action: BaseAction | None = None,
        *,
        raise_on_failure: bool | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Execute an action, either by passing a BaseAction as the first argument, or by passing action fields as kwargs.
        """
        step_action = parse_action(action, **kwargs)

        message = None
        exception = None
        scraped_data = None
        resolved_action = None

        with TimedSpan.capture() as span:
            try:
                # --------------------------------
                # --- Step 1: action resolution --
                # --------------------------------

                resolved_action = await resolve_action(step_action, self._snapshot, verbose=config.verbose)
                if config.verbose:
                    logger.info(f"🌌 starting execution of action '{resolved_action.type}' ...")
                # --------------------------------
                # ----- Step 2: execution -------
                # --------------------------------

                message = resolved_action.execution_message()
                exception: Exception | None = None

                match resolved_action:
                    case ScrapeAction():
                        raise ScrapeIsNotAnActionError()
                    case EvaluateJsAction(code=code):
                        # Evaluate JavaScript code on the page and return the result.
                        # The guard runs code with a top-level `return` as a function body.
                        guard_token = new_guard_token()
                        try:
                            evaluate_kwargs: dict[str, bool] = {}
                            if config.browser_backend == BrowserBackend.PATCHRIGHT:
                                evaluate_kwargs["isolated_context"] = False
                            # The guard measures the value inside the page and
                            # throws past the budget, so an oversized result is
                            # never serialized by the browser, decoded by the
                            # driver, or rebuilt as Python objects.
                            result = await asyncio.wait_for(
                                self.window.page.evaluate(
                                    PAGE_RESULT_GUARD,
                                    [
                                        page_expression(code),
                                        config.evaluate_js_max_result_bytes,
                                        config.evaluate_js_max_result_values,
                                        guard_token,
                                    ],
                                    **evaluate_kwargs,
                                ),
                                timeout=config.timeout_evaluate_js_ms / 1000.0,
                            )
                        except asyncio.TimeoutError:
                            success = False
                            message = f"JavaScript evaluation timed out after {config.timeout_evaluate_js_ms}ms"
                        except PlaywrightError as js_err:
                            limit_reason = page_limit_reason(str(js_err), guard_token)
                            if limit_reason is not None:
                                raise EvaluateJsResultLimitError(
                                    config.evaluate_js_max_result_bytes, limit_reason
                                ) from None
                            success = False
                            message = f"JavaScript evaluation failed: {js_err}"
                        else:
                            result_str: str | None = None
                            try:
                                # The guard returns the result as one JSON string,
                                # decoded once here instead of value by value by
                                # Playwright, which cost several times the memory.
                                result = decode_page_result(
                                    result,
                                    guard_token,
                                    max_bytes=config.evaluate_js_max_result_bytes,
                                    max_values=config.evaluate_js_max_result_values,
                                )
                                result_str = format_evaluation_result(
                                    result, max_bytes=config.evaluate_js_max_result_bytes
                                )
                            except InvalidPagePayloadError as payload_err:
                                message = f"JavaScript evaluation failed: {payload_err}"
                            finally:
                                # The action's frame can itself be retained when a
                                # failure is raised later or saved in the trajectory.
                                result = None
                            success = result_str is not None
                            if result_str is not None:
                                scraped_data = DataSpace(markdown=result_str)
                    case ToolAction():
                        raise InboxActionNotSupportedLocallyError(resolved_action)
                    case _:
                        resolved_action = await self._action_with_vault(resolved_action)
                        # interactions bound themselves by `action.timeout` (see execution.py)
                        success = await execution.execute(
                            self.window,
                            resolved_action,
                            storage=self.storage,
                            prev_snapshot=self._snapshot,
                            verbose=self._verbose,
                        )
                        if not success:
                            # `message` still holds the success-phrased execution_message.
                            message = f"Action '{resolved_action.type}' failed during browser execution"

            except (
                NoSnapshotObservedError,
                NoStorageObjectProvidedError,
                InboxActionNotSupportedLocallyError,
                ScrapeIsNotAnActionError,
            ):
                # this should be handled by the caller
                raise
            except InvalidActionError as e:
                success = False
                message = e.dev_message
                exception = e
            except RateLimitError as e:
                success = False
                message = "Rate limit reached. Waiting before retry."
                exception = e
            except asyncio.TimeoutError as e:
                success = False
                message = "Action timed out."
                exception = e
            except NotteBaseError as e:
                if isinstance(e, EvaluateJsResultLimitError):
                    # Saved failures must not own the formatter's recursive frames
                    # and their references to the rejected browser result.
                    e.__traceback__ = None
                # When raise_on_failure is True, we use the dev message to give more details to the user
                success = False
                message = e.dev_message
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
            # resolution failed: keep the initial action in the trajectory
            resolved_action = step_action

        if not success and exception is None:
            # Actions that signal failure by returning (a tool returning `success=False`,
            # a controller action returning `False`) carry no exception. Synthesize one
            # before the result is built so the returned result, the trajectory and the
            # raise below all agree on what failed.
            exception = ActionExecutionError(
                action_id=resolved_action.type,
                url=self._window.page.url if self._window is not None else "",
                reason=message or "unknown",
            )

        execution_result = ExecutionResult(
            action=resolved_action,
            success=success,
            message=message,
            data=scraped_data,
            exception=exception,
            started_at=span.started_at,
            ended_at=span.close().ended_at,
        )
        await self.trajectory.append(execution_result)

        _raise_on_failure = raise_on_failure if raise_on_failure is not None else self.default_raise_on_failure
        # Gate on "did the action fail", not "did something throw": after the synthesis
        # above, every failure carries an exception, including the return-style ones
        # that were previously silently swallowed, the way evaluate_js was.
        if _raise_on_failure and exception is not None:
            raise exception
        return execution_result

    # BEGIN GENERATED OVERLOADS: execute (scripts/generate_action_overloads.py)
    @overload
    def execute(self, action: BaseAction, *, raise_on_failure: bool | None = None) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[FormFillActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GotoActionDict]) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GotoNewTabActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CloseTabActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[SwitchTabActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GoBackActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GoForwardActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ReloadActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[WaitActionDict]) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[PressKeyActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ScrollUpActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ScrollDownActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CaptchaSolveActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[EvaluateJsActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ClickActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[FillActionDict]) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[MultiFactorFillActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[FallbackFillActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CheckActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[SelectDropdownOptionActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[UploadFileActionDict]
    ) -> ExecutionResult: ...
    @overload
    def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[DownloadFileActionDict]
    ) -> ExecutionResult: ...

    # END GENERATED OVERLOADS: execute

    def execute(
        self,
        action: BaseAction | None = None,
        *,
        raise_on_failure: bool | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Synchronous version of aexecute, supporting both BaseAction and action fields as kwargs.
        """

        return asyncio.run(
            self.aexecute(action=action, raise_on_failure=raise_on_failure, **kwargs)  # pyright: ignore [reportArgumentType]
        )

    # raise_on_failure=True (default) -> the evaluated string; failures raise
    @overload
    async def aevaluate_js(self, code: str, *, raise_on_failure: Literal[True] = ...) -> str: ...

    # raise_on_failure=False -> the ExecutionResult envelope, like execute()
    @overload
    async def aevaluate_js(self, code: str, *, raise_on_failure: Literal[False]) -> ExecutionResult: ...

    async def aevaluate_js(self, code: str, *, raise_on_failure: bool = True) -> str | ExecutionResult:
        """
        Evaluate JavaScript on the current page and return its result as a string.

        The result is stringified the way `evaluate_js` records it: objects and
        arrays as JSON, a JS `null` as the string `"null"`. On failure the typed
        exception is raised with the actual JavaScript error; pass
        `raise_on_failure=False` to get the `ExecutionResult` envelope instead.
        """
        result = await self.aexecute(type="evaluate_js", code=code, raise_on_failure=raise_on_failure)
        if not raise_on_failure:
            return result
        if result.data is None:
            # cannot happen with this package's execute path, which always sets
            # data on a successful eval; a typed error beats a stripped assert
            raise EvaluateJsNoDataError()
        return result.data.markdown

    @overload
    def evaluate_js(self, code: str, *, raise_on_failure: Literal[True] = ...) -> str: ...

    @overload
    def evaluate_js(self, code: str, *, raise_on_failure: Literal[False]) -> ExecutionResult: ...

    def evaluate_js(self, code: str, *, raise_on_failure: bool = True) -> str | ExecutionResult:
        """
        Synchronous version of aevaluate_js.
        """
        return asyncio.run(self.aevaluate_js(code, raise_on_failure=raise_on_failure))

    async def afetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: FetchData | None = None,
        timeout: float | None = None,
    ) -> requests.Response:
        """
        Issue an HTTP request from the page the session is on and return the response.

        The request runs inside the browser through `fetch()`, so it carries the
        page's cookies, the session's proxy and the browser's own network
        fingerprint. A relative `url` resolves against the current page, which
        also makes it same-origin; a cross-origin URL is subject to CORS exactly
        as in a browser tab, so `goto` the target origin first. Redirects are
        followed and the final URL is on `response.url`. The result is a standard
        `requests.Response`: a non-2xx status is returned, not raised, and
        `response.raise_for_status()` raises `requests.HTTPError`. A network
        failure surfaces as the JavaScript error.

        `json` is serialised as the body with an `application/json` content type,
        `data` as a form body when it is a mapping or verbatim when it is a string.
        """
        script = build_fetch_script(
            url, method=method, headers=headers, params=params, json_body=json, data=data, timeout=timeout
        )
        return response_from_evaluated(await self.aevaluate_js(script))

    def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: FetchData | None = None,
        timeout: float | None = None,
    ) -> requests.Response:
        """
        Synchronous version of afetch.
        """
        return asyncio.run(
            self.afetch(url, method=method, headers=headers, params=params, json=json, data=data, timeout=timeout)
        )

    # response_format provided, raise_on_failure=True (default) -> unwrapped TBaseModel
    @overload
    async def ascrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> TBaseModel: ...

    # response_format provided, raise_on_failure=False -> wrapped StructuredData[TBaseModel]
    @overload
    async def ascrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    # instructions only, raise_on_failure=True (default) -> unwrapped BaseModel
    @overload
    async def ascrape(
        self, *, instructions: str, raise_on_failure: Literal[True] = ..., **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> BaseModel: ...

    # instructions only, raise_on_failure=False -> wrapped StructuredData[BaseModel]
    @overload
    async def ascrape(
        self, *, instructions: str, raise_on_failure: Literal[False], **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> StructuredData[BaseModel]: ...

    # markdown catch-all LAST: open Unpack[TypedDict] otherwise swallows every kwargs call under ty
    @overload
    async def ascrape(self, /, *, raise_on_failure: bool = True, **params: Unpack[ScrapeMarkdownParamsDict]) -> str: ...

    @timeit("scrape")
    @track_usage("local.session.scrape")
    async def ascrape(
        self, *, raise_on_failure: bool = True, **params: Unpack[ScrapeParamsDict]
    ) -> StructuredData[BaseModel] | BaseModel | str:
        # Extract and convert response_format for the action (store as JSON schema)
        response_format = params.get("response_format")
        instructions = params.get("instructions")
        response_format_schema: dict[str, Any] | None = None
        is_structured_scrape = instructions is not None or response_format is not None
        if response_format is not None:
            response_format_schema = response_format.model_json_schema()

        # Create ScrapeAction for trajectory recording
        scrape_action = ScrapeAction(
            instructions=instructions,
            only_main_content=params.get("only_main_content", False),
            selector=params.get("selector"),
            scrape_links=params.get("scrape_links", True),
            scrape_images=params.get("scrape_images", False),
            ignored_tags=params.get("ignored_tags"),
            response_format=response_format_schema,
        )

        exception: Exception | None = None
        data: DataSpace | None = None
        with TimedSpan.capture() as span:
            try:
                async with profiler.profile("NotteSession._ascrape", service_name="execution"):
                    scrape_params = ScrapeParams.model_validate(params)
                    data = await scrape_page(self.window, scrape_params, get_extractor=self._get_extractor)
            except Exception as e:
                exception = e
                # Record failure to trajectory
                execution_result = ExecutionResult(
                    action=scrape_action,
                    success=False,
                    message=scrape_action.execution_message(),
                    data=None,
                    exception=exception,
                    started_at=span.started_at,
                    ended_at=span.close().ended_at,
                )
                await self.trajectory.append(execution_result)
                if raise_on_failure:
                    raise

                # return meaningful data when exception occurred
                error_message = f"No markdown available. Exception: {exception}"

                retval = (  # pyright: ignore [reportUnknownVariableType]
                    StructuredData(success=False, error=error_message, data=None)
                    if is_structured_scrape
                    else error_message
                )

                return retval  # pyright: ignore [reportUnknownVariableType]

        # Record to trajectory
        execution_result = ExecutionResult(
            action=scrape_action,
            # success is True if structured_scrape_failed is False, otherwise False
            success=not data.structured_scrape_failed if is_structured_scrape else True,
            message=scrape_action.execution_message(),
            data=data,
            exception=data.structured_scrape_exception if is_structured_scrape else None,
            started_at=span.started_at,
            ended_at=span.close().ended_at,
        )
        await self.trajectory.append(execution_result)

        # Return data
        if is_structured_scrape:
            if data.structured is None:
                raise ScrapeFailedError("Failed to extract structured data")
            if raise_on_failure:  # the following line raises ScrapeFailedError if failed
                return data.structured.get()
            if isinstance(data.structured.data, RootModel):
                data.structured.data = data.structured.data.root  # type: ignore[attr-defined]
            return data.structured
        return data.markdown

    def _get_extractor(self) -> StructuredExtractor:
        # Resolved on first structured scrape so that sessions never load an LLM unless they need one.
        if self._extractor is None:
            self._extractor = default_extractor()
        return self._extractor

    # response_format provided, raise_on_failure=True (default) -> unwrapped TBaseModel
    @overload
    def scrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> TBaseModel: ...

    # response_format provided, raise_on_failure=False -> wrapped StructuredData[TBaseModel]
    @overload
    def scrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    # instructions only, raise_on_failure=True (default) -> unwrapped BaseModel as dict
    @overload
    def scrape(
        self, *, instructions: str, raise_on_failure: Literal[True] = ..., **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> dict[str, Any]: ...

    # instructions only, raise_on_failure=False -> wrapped StructuredData[BaseModel]
    @overload
    def scrape(
        self, *, instructions: str, raise_on_failure: Literal[False], **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> StructuredData[BaseModel]: ...

    # markdown catch-all LAST: open Unpack[TypedDict] otherwise swallows every kwargs call under ty
    @overload
    def scrape(self, /, *, raise_on_failure: bool = True, **params: Unpack[ScrapeMarkdownParamsDict]) -> str: ...

    def scrape(
        self, *, raise_on_failure: bool = True, **params: Unpack[ScrapeParamsDict]
    ) -> StructuredData[BaseModel] | BaseModel | dict[str, Any] | str:
        return asyncio.run(self.ascrape(raise_on_failure=raise_on_failure, **params))

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
