"""Async sessions endpoint client for the Notte SDK."""
# pyright: reportImportCycles=false, reportImplicitOverride=false, reportMissingSuperCall=false, reportOverlappingOverload=false, reportUnusedParameter=false, reportUnreachable=false

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Unpack, overload
from urllib.parse import urljoin
from webbrowser import open as open_browser

from notte_core.actions import BaseAction, InteractionActionUnion
from notte_core.actions.typedicts import (
    CaptchaSolveActionDict,
    CheckActionDict,
    ClickActionDict,
    CloseTabActionDict,
    CompletionActionDict,
    DownloadFileActionDict,
    EmailReadActionDict,
    EvaluateJsActionDict,
    FallbackFillActionDict,
    FillActionDict,
    FormFillActionDict,
    GoBackActionDict,
    GoForwardActionDict,
    GotoActionDict,
    GotoNewTabActionDict,
    HelpActionDict,
    MultiFactorFillActionDict,
    PressKeyActionDict,
    ReloadActionDict,
    ScrapeActionDict,
    ScrollDownActionDict,
    ScrollUpActionDict,
    SelectDropdownOptionActionDict,
    SmsReadActionDict,
    SwitchTabActionDict,
    UploadFileActionDict,
    WaitActionDict,
    action_dict_to_base_action,
)
from notte_core.browser.observation import ExecutionResult
from notte_core.common.config import CookieDict, PerceptionType, config
from notte_core.common.logging import logger
from notte_core.common.resource import AsyncResource
from notte_core.common.telemetry import track_usage
from notte_core.data.space import ImageData, StructuredData, TBaseModel
from notte_core.utils.files import create_or_append_cookies_to_file
from notte_core.utils.webp_replay import MP4Replay
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk._async.base import AsyncBaseClient, NotteEndpoint
from notte_sdk._async.files import AsyncRemoteFileStorage
from notte_sdk._async.http import AsyncHTTPClient
from notte_sdk._async.page import AsyncPageClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import (
    ExecutionRequest,
    GetCookiesResponse,
    ObserveRequestDict,
    ObserveResponse,
    PaginationParamsDict,
    ScrapeMarkdownParamsDict,
    ScrapeRequestDict,
    SessionDebugResponse,
    SessionListRequest,
    SessionListRequestDict,
    SessionOffsetResponse,
    SessionResponse,
    SessionStartRequest,
    SessionStartRequestDict,
    SetCookiesRequest,
    SetCookiesResponse,
    TabSessionDebugRequest,
    TabSessionDebugResponse,
)
from notte_sdk.websockets.base import WebsocketService
from notte_sdk.websockets.jupyter import display_image_in_notebook

if TYPE_CHECKING:
    from notte_sdk._async.client import AsyncNotteClient

# Retry configuration constants
CLUSTER_OVERLOAD_RETRY_DELAY = 30  # seconds to wait before retrying on 529 errors

# Playwright imports (optional)
_async_playwright_available = False

try:
    from playwright.async_api import Browser as BrowserAsync
    from playwright.async_api import Page as PageAsync
    from playwright.async_api import Playwright as PlaywrightAsync
    from playwright.async_api import async_playwright as _async_playwright

    _async_playwright_available = True
except ImportError:
    _async_playwright = None


class SessionViewerType(StrEnum):
    CDP = "cdp"
    BROWSER = "browser"
    JUPYTER = "jupyter"


@final
class AsyncSessionsClient(AsyncBaseClient):
    """Async client for session management."""

    # Session endpoints
    SESSION_START = "start"
    SESSION_STOP = "{session_id}/stop"
    SESSION_STATUS = "{session_id}"
    SESSION_LIST = ""
    SESSION_VIEWER = "viewer"

    # Cookie endpoints
    SESSION_SET_COOKIES = "{session_id}/cookies"
    SESSION_GET_COOKIES = "{session_id}/cookies"

    # Debug endpoints
    SESSION_DEBUG = "{session_id}/debug"
    SESSION_DEBUG_TAB = "{session_id}/debug/tab"
    SESSION_DEBUG_REPLAY = "{session_id}/replay"
    SESSION_DEBUG_OFFSET = "{session_id}/offset"

    def __init__(
        self,
        root_client: "AsyncNotteClient",
        http_client: AsyncHTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
        viewer_type: SessionViewerType = SessionViewerType.BROWSER,
    ):
        """Initialize AsyncSessionsClient."""
        super().__init__(
            root_client=root_client,
            base_endpoint_path="sessions",
            http_client=http_client,
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )
        self.page: AsyncPageClient = AsyncPageClient(
            root_client=root_client,
            http_client=http_client,
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )
        self.viewer_type: SessionViewerType = viewer_type

    @staticmethod
    def _session_start_endpoint() -> NotteEndpoint[SessionResponse]:
        return NotteEndpoint(path=AsyncSessionsClient.SESSION_START, response=SessionResponse, method="POST")

    @staticmethod
    def _session_stop_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        path = AsyncSessionsClient.SESSION_STOP
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="DELETE")

    @staticmethod
    def _session_status_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        path = AsyncSessionsClient.SESSION_STATUS
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="GET")

    @staticmethod
    def _session_list_endpoint(params: SessionListRequest | None = None) -> NotteEndpoint[SessionResponse]:
        return NotteEndpoint(
            path=AsyncSessionsClient.SESSION_LIST,
            response=SessionResponse,
            method="GET",
            request=None,
            params=params,
        )

    @staticmethod
    def _session_debug_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionDebugResponse]:
        path = AsyncSessionsClient.SESSION_DEBUG
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionDebugResponse, method="GET")

    @staticmethod
    def _session_debug_tab_endpoint(
        session_id: str | None = None, params: TabSessionDebugRequest | None = None
    ) -> NotteEndpoint[TabSessionDebugResponse]:
        path = AsyncSessionsClient.SESSION_DEBUG_TAB
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=TabSessionDebugResponse, method="GET", params=params)

    @staticmethod
    def _session_debug_replay_endpoint(session_id: str | None = None) -> NotteEndpoint[BaseModel]:
        path = AsyncSessionsClient.SESSION_DEBUG_REPLAY
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=BaseModel, method="GET")

    @staticmethod
    def _session_debug_offset_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionOffsetResponse]:
        path = AsyncSessionsClient.SESSION_DEBUG_OFFSET
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionOffsetResponse, method="GET")

    @staticmethod
    def _session_set_cookies_endpoint(session_id: str | None = None) -> NotteEndpoint[SetCookiesResponse]:
        path = AsyncSessionsClient.SESSION_SET_COOKIES
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SetCookiesResponse, method="POST")

    @staticmethod
    def _session_get_cookies_endpoint(session_id: str | None = None) -> NotteEndpoint[GetCookiesResponse]:
        path = AsyncSessionsClient.SESSION_GET_COOKIES
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=GetCookiesResponse, method="GET")

    @track_usage("cloud.session.start")
    async def start(self, **data: Unpack[SessionStartRequestDict]) -> SessionResponse:
        """Start a new session."""
        request = SessionStartRequest.model_validate(data)
        return await self.request(AsyncSessionsClient._session_start_endpoint().with_request(request))

    @track_usage("cloud.session.stop")
    async def stop(self, session_id: str) -> SessionResponse:
        """Stop an active session."""
        logger.info(f"[Session] {session_id} is stopping")
        endpoint = AsyncSessionsClient._session_stop_endpoint(session_id=session_id)
        response = await self.request(endpoint)
        if response.status != "closed":
            raise RuntimeError(f"[Session] {session_id} failed to stop")
        logger.info(f"[Session] {session_id} stopped")
        return response

    @track_usage("cloud.session.status")
    async def status(self, session_id: str) -> SessionResponse:
        """Get the status of a session."""
        endpoint = AsyncSessionsClient._session_status_endpoint(session_id=session_id)
        return await self.request(endpoint)

    @track_usage("cloud.session.cookies.set")
    async def set_cookies(
        self,
        session_id: str,
        cookies: list[CookieDict] | None = None,
        cookie_file: str | Path | None = None,
    ) -> SetCookiesResponse:
        """Upload cookies to the session."""
        endpoint = AsyncSessionsClient._session_set_cookies_endpoint(session_id=session_id)

        if cookies is not None and cookie_file is not None:
            raise ValueError("Cannot provide both cookies and cookie_file")

        if cookies is not None:
            request = SetCookiesRequest.model_validate(dict(cookies=cookies))
        elif cookie_file is not None:
            request = SetCookiesRequest.from_json(cookie_file)
        else:
            raise ValueError("Have to provide either cookies or cookie_file")

        return await self.request(endpoint.with_request(request))

    @track_usage("cloud.session.cookies.get")
    async def get_cookies(self, session_id: str) -> GetCookiesResponse:
        """Get cookies from the session."""
        endpoint = AsyncSessionsClient._session_get_cookies_endpoint(session_id=session_id)
        return await self.request(endpoint)

    @track_usage("cloud.session.list")
    async def list(self, **data: Unpack[SessionListRequestDict]) -> Sequence[SessionResponse]:
        """List sessions."""
        params = SessionListRequest.model_validate(data)
        endpoint = AsyncSessionsClient._session_list_endpoint(params=params)
        return await self.request_list(endpoint)

    @track_usage("cloud.session.debug")
    async def debug_info(self, session_id: str) -> SessionDebugResponse:
        """Get debug information for a session."""
        endpoint = AsyncSessionsClient._session_debug_endpoint(session_id=session_id)
        return await self.request(endpoint)

    @track_usage("cloud.session.debug.tab")
    async def debug_tab_info(self, session_id: str, tab_idx: int | None = None) -> TabSessionDebugResponse:
        """Get debug information for a specific tab."""
        params = TabSessionDebugRequest(tab_idx=tab_idx) if tab_idx is not None else None
        endpoint = AsyncSessionsClient._session_debug_tab_endpoint(session_id=session_id, params=params)
        return await self.request(endpoint)

    @track_usage("cloud.session.offset")
    async def offset(self, session_id: str) -> SessionOffsetResponse:
        """Get the trajectory offset for the session."""
        endpoint = AsyncSessionsClient._session_debug_offset_endpoint(session_id=session_id)
        return await self.request(endpoint)

    @track_usage("cloud.session.replay")
    async def replay(self, session_id: str) -> MP4Replay:
        """Download the replay for the session."""
        endpoint = AsyncSessionsClient._session_debug_replay_endpoint(session_id=session_id)
        file_bytes = await self._request_file(endpoint, file_type="mp4")
        return MP4Replay(file_bytes)

    @track_usage("cloud.session.viewer.browser")
    def viewer_browser(self, session_id: str, _viewer_url: str | None = None) -> None:
        """Open live session replay in browser."""
        # Note: This is sync because it just opens a browser
        if _viewer_url is None:
            raise ValueError("viewer_url must be provided for async client. Use debug_info() to get it.")
        _ = open_browser(_viewer_url, new=1)

    @track_usage("cloud.session.viewer.notebook")
    async def viewer_notebook(self, session_id: str) -> WebsocketService:
        """Get a WebsocketService for Jupyter notebook display."""
        debug_info = await self.debug_info(session_id=session_id)
        return WebsocketService(wss_url=debug_info.ws.recording, process=display_image_in_notebook)

    @track_usage("cloud.session.viewer.cdp")
    async def viewer_cdp(self, session_id: str) -> None:
        """Open browser tab with debug URL."""
        debug_info = await self.debug_info(session_id=session_id)
        _ = open_browser(debug_info.debug_url)


class AsyncRemoteSession(AsyncResource):
    """Async remote session that can be managed through the Notte API."""

    @overload
    def __init__(
        self,
        *,
        storage: AsyncRemoteFileStorage | None = None,
        perception_type: PerceptionType = config.perception_type,
        raise_on_failure: bool = config.raise_on_session_execution_failure,
        cookie_file: str | Path | None = None,
        open_viewer: bool = False,
        _client: AsyncSessionsClient | None = None,
        **data: Unpack[SessionStartRequestDict],
    ) -> None: ...

    @overload
    def __init__(self, /, session_id: str, *, _client: AsyncSessionsClient | None = None) -> None: ...

    def __init__(
        self,
        session_id: str | None = None,
        *,
        storage: AsyncRemoteFileStorage | None = None,
        perception_type: PerceptionType = config.perception_type,
        cookie_file: str | Path | None = None,
        raise_on_failure: bool = config.raise_on_session_execution_failure,
        open_viewer: bool = False,
        _client: AsyncSessionsClient | None = None,
        **data: Unpack[SessionStartRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("AsyncSessionsClient is required")

        request_data = {k: v for k, v in data.items() if k != "open_viewer"}
        request = SessionStartRequest.model_validate(request_data)

        if storage is not None:
            request.use_file_storage = True

        self.request: SessionStartRequest = request
        self._open_viewer: bool = open_viewer
        self._session_id: str | None = session_id

        self.client: AsyncSessionsClient = _client
        self.response: SessionResponse | None = None
        self.storage: AsyncRemoteFileStorage | None = storage
        self.default_perception_type: PerceptionType = perception_type
        self.default_raise_on_failure: bool = raise_on_failure
        self._cookie_file: Path | None = Path(cookie_file) if cookie_file is not None else None

        # Async playwright instances
        self._async_playwright_context: "PlaywrightAsync | None" = None
        self._async_playwright_browser: "BrowserAsync | None" = None
        self._async_playwright_page: "PageAsync | None" = None

        if self.storage is not None and not self.request.use_file_storage:
            logger.warning(
                "Storage is provided but `use_file_storage=False` in session start request. Overriding `use_file_storage=True`."
            )
            self.request.use_file_storage = True

    async def __aenter__(self) -> "AsyncRemoteSession":
        await self.astart()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        if exc_val is not None:
            logger.warning(f"Session exiting because of exception: {exc_val}")

        # Clean up async playwright resources
        if self._async_playwright_browser is not None:
            await self._async_playwright_browser.close()
            self._async_playwright_browser = None
        if self._async_playwright_context is not None:
            await self._async_playwright_context.stop()
            self._async_playwright_context = None
        self._async_playwright_page = None

        await self.astop()

        if isinstance(exc_val, KeyboardInterrupt):
            raise KeyboardInterrupt() from None

    @override
    async def astart(self, tries: int = 3) -> None:
        """Start the session."""
        if self._session_id is not None:
            # Resuming existing session
            self.response = await self.client.status(session_id=self._session_id)
            if self.storage is not None:
                self.storage.set_session_id(self._session_id)
            return

        if self.response is not None:
            raise ValueError("Session already started")

        orig_tries = tries
        while tries > 0:
            tries -= 1
            try:
                self.response = await self.client.start(**self.request.model_dump())
                break
            except NotteAPIError as e:
                status: int | None = e.error.get("status")

                if tries == 0:
                    raise

                if status is None or 400 <= status < 500:
                    raise

                retry_str = f"{orig_tries - tries}/{orig_tries - 1}"
                if status == 529:
                    logger.warning(
                        f"Failed to start session due to cluster overload, retrying in {CLUSTER_OVERLOAD_RETRY_DELAY} seconds ({retry_str})..."
                    )
                    await asyncio.sleep(CLUSTER_OVERLOAD_RETRY_DELAY)
                else:
                    logger.warning(f"Failed to start session: retrying ({retry_str})")

        if self.storage is not None:
            self.storage.set_session_id(self.session_id)

        logger.info(f"[Session] {self.session_id} started with request: {self.request.model_dump(exclude_none=True)}")

        if self._open_viewer:
            await self.viewer()

        # Try to load cookies from file
        if self._cookie_file is not None:
            if Path(self._cookie_file).exists():
                logger.info(f"Automatically loading cookies from {self._cookie_file}")
                _ = await self.set_cookies(cookie_file=self._cookie_file)
            else:
                logger.warning(f"Cookie file {self._cookie_file} not found, skipping cookie loading")

    @override
    async def astop(self) -> None:
        """Stop the session."""
        if self._cookie_file is not None:
            try:
                cookies = await self.get_cookies()
                create_or_append_cookies_to_file(self._cookie_file, cookies)
            except Exception as e:
                logger.error(f"Error saving cookies to {self._cookie_file}: {e}")
        self.response = await self.client.stop(session_id=self.session_id)

    @property
    def session_id(self) -> str:
        """Get the session ID."""
        if self.response is None:
            raise ValueError("You need to start the session first to get the session id")
        return self.response.session_id

    async def offset(self) -> int:
        """Get the trajectory offset."""
        result = await self.client.offset(session_id=self.session_id)
        return result.offset

    async def replay(self) -> MP4Replay:
        """Get the session replay."""
        return await self.client.replay(session_id=self.session_id)

    async def viewer_browser(self) -> None:
        """Open live session replay in browser."""
        debug_info = await self.client.debug_info(session_id=self.session_id)
        base_url = urljoin(self.client.server_url + "/", f"{self.client.base_endpoint_path}/viewer/")
        _viewer_url = urljoin(base_url, f"index.html?ws={debug_info.ws.recording}")
        self.client.viewer_browser(self.session_id, _viewer_url=_viewer_url)

    async def viewer_notebook(self) -> WebsocketService:
        """Get WebsocketService for Jupyter notebook."""
        return await self.client.viewer_notebook(session_id=self.session_id)

    async def viewer_cdp(self) -> None:
        """Open browser tab with debug URL."""
        await self.client.viewer_cdp(session_id=self.session_id)

    async def viewer(self) -> None:
        """Open the viewer based on viewer_type."""
        match self.client.viewer_type:
            case SessionViewerType.BROWSER:
                await self.viewer_browser()
            case SessionViewerType.JUPYTER:
                _ = await self.viewer_notebook()
            case SessionViewerType.CDP:
                await self.viewer_cdp()

    async def status(self) -> SessionResponse:
        """Get the current session status."""
        return await self.client.status(session_id=self.session_id)

    async def set_cookies(
        self,
        cookies: list[CookieDict] | None = None,
        cookie_file: str | Path | None = None,
    ) -> SetCookiesResponse:
        """Upload cookies to the session."""
        return await self.client.set_cookies(session_id=self.session_id, cookies=cookies, cookie_file=cookie_file)

    async def get_cookies(self) -> list[CookieDict]:
        """Get cookies from the session."""
        response = await self.client.get_cookies(session_id=self.session_id)
        return [cookie.model_dump() for cookie in response.cookies]  # type: ignore

    async def debug_info(self) -> SessionDebugResponse:
        """Get debug information for the session."""
        return await self.client.debug_info(session_id=self.session_id)

    async def cdp_url(self) -> str:
        """Get the Chrome DevTools Protocol WebSocket URL."""
        if self.response is None:
            raise ValueError("You need to start the session first to get the cdp url")
        if self.request.cdp_url is not None:
            return self.request.cdp_url
        if self.response.cdp_url is not None:
            return self.response.cdp_url
        debug = await self.debug_info()
        return debug.ws.cdp

    @property
    async def apage(self) -> "PageAsync":
        """Get an async Playwright page connected via CDP."""
        if not _async_playwright_available:
            raise ImportError("Playwright not installed. Use `pip install notte-sdk[playwright]` to install it.")

        if self._async_playwright_page is not None:
            return self._async_playwright_page

        try:
            if self._async_playwright_context is None:
                if _async_playwright is None:
                    raise RuntimeError("Playwright is not initialized")
                self._async_playwright_context = await _async_playwright().start()

            if self._async_playwright_browser is None:
                cdp_url = await self.cdp_url()
                self._async_playwright_browser = await self._async_playwright_context.chromium.connect_over_cdp(cdp_url)

            self._async_playwright_page = self._async_playwright_browser.contexts[0].pages[0]
            return self._async_playwright_page
        except Exception as e:
            raise RuntimeError("Failed to access the async playwright page from CDP") from e

    # Page operations

    @overload
    async def scrape(self, /, *, raise_on_failure: bool = True, **params: Unpack[ScrapeMarkdownParamsDict]) -> str: ...

    @overload
    async def scrape(
        self, *, instructions: str, raise_on_failure: Literal[True] = ..., **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> dict[str, Any]: ...

    @overload
    async def scrape(
        self, *, instructions: str, raise_on_failure: Literal[False], **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> StructuredData[BaseModel]: ...

    @overload
    async def scrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> TBaseModel: ...

    @overload
    async def scrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    @overload
    async def scrape(self, /, *, only_images: Literal[True], raise_on_failure: bool = True) -> list[ImageData]: ...

    async def scrape(
        self, *, raise_on_failure: bool = True, **data: Unpack[ScrapeRequestDict]
    ) -> StructuredData[BaseModel] | BaseModel | dict[str, Any] | str | list[ImageData]:
        """Scrape the current page."""
        return await self.client.page.scrape(self.session_id, raise_on_failure=raise_on_failure, **data)

    @overload
    async def observe(
        self,
        *,
        instructions: str,
        url: str | None = None,
        perception_type: PerceptionType | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> list[InteractionActionUnion]: ...

    @overload
    async def observe(
        self,
        *,
        instructions: None = None,
        url: str | None = None,
        perception_type: PerceptionType | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> ObserveResponse: ...

    async def observe(self, **data: Unpack[ObserveRequestDict]) -> ObserveResponse | list[InteractionActionUnion]:
        """Observe the current page."""
        if data.get("perception_type") is None:
            data["perception_type"] = self.default_perception_type
        return await self.client.page.observe(session_id=self.session_id, **data)  # type: ignore

    # Execute action overloads
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[FormFillActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GotoActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GotoNewTabActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CloseTabActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[SwitchTabActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GoBackActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[GoForwardActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ReloadActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[WaitActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[PressKeyActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ScrollUpActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ScrollDownActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CaptchaSolveActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[HelpActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CompletionActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ScrapeActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[EmailReadActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[SmsReadActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[EvaluateJsActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[ClickActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[FillActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[MultiFactorFillActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[FallbackFillActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[CheckActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[SelectDropdownOptionActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[UploadFileActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[DownloadFileActionDict]
    ) -> ExecutionResult: ...
    @overload
    async def execute(self, action: BaseAction, *, raise_on_failure: bool | None = None) -> ExecutionResult: ...

    async def execute(
        self,
        action: BaseAction | None = None,
        *,
        raise_on_failure: bool | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """Execute an action on the current page."""
        # Fast path: if action is already a BaseAction, use it directly
        if isinstance(action, BaseAction):
            action_obj = action
        elif kwargs:
            if "type" not in kwargs:
                raise ValueError("Missing required action field: 'type'")
            action_obj = action_dict_to_base_action(kwargs)  # type: ignore[arg-type]
        elif action is None:
            raise ValueError("No action provided")
        else:
            action_obj = ExecutionRequest.get_action(action=action, data=None)

        result = await self.client.page.execute(session_id=self.session_id, action=action_obj)

        _raise_on_failure = raise_on_failure if raise_on_failure is not None else self.default_raise_on_failure
        if _raise_on_failure and result.exception is not None:
            logger.error(f"Execution failed with message: '{result.message}'")
            raise result.exception

        return result
