import asyncio
import os
import random
import time
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, Unpack, overload
from urllib.parse import urlsplit
from webbrowser import open as open_browser

from notte_core import __version__ as notte_core_version
from notte_core.actions import BaseAction, InteractionActionUnion
from notte_core.actions.typedicts import (
    CaptchaSolveActionDict,
    CheckActionDict,
    ClickActionDict,
    CloseTabActionDict,
    DownloadFileActionDict,
    EmailVerificationReadActionDict,
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
    action_dict_to_base_action,
)
from notte_core.config import CookieDict, PerceptionType, config, create_or_append_cookies_to_file
from notte_core.data import StructuredData, TBaseModel
from notte_core.errors import EvaluateJsNoDataError, NotteBaseError
from notte_core.fetch import FetchData, FetchResponse, build_fetch_script, response_from_evaluated
from notte_core.logging import logger
from notte_core.observation import ExecutionResult
from notte_core.resource import SyncResource
from notte_core.telemetry import track_usage
from notte_core.types import (
    Cookie,
    ExecutionRequest,
    ObserveRequestDict,
    ObserveResponse,
    PaginationParamsDict,
    ScrapeMarkdownParamsDict,
    ScrapeRequestDict,
    TabSessionDebugRequest,
)
from pydantic import BaseModel
from typing_extensions import Self, final, override

from notte_sdk._flow import Call, Flow, Sleep, arun, run
from notte_sdk._generated import operations as api
from notte_sdk._generated.public import (
    GetCookiesResponse,
    ProfileResponse,
    ReplayResponse,
    SessionDebugResponse,
    SessionProfileSaveRequestDict,
    SessionResponse,
    SessionStartRequest,
    SessionStartRequestDict,
    SessionStopRequestDict,
    SetCookiesRequest,
    SetCookiesResponse,
    TabSessionDebugResponse,
)
from notte_sdk._generated.resources import AsyncSessionsOperations, SessionsOperations
from notte_sdk._retry import is_retryable_status
from notte_sdk._transport import TransportError
from notte_sdk.endpoints.base import NotteEndpoint
from notte_sdk.endpoints.files import AsyncRemoteFileStorage, RemoteFileStorage
from notte_sdk.endpoints.page import AsyncPageClient, PageClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.websockets.base import WebsocketService
from notte_sdk.websockets.jupyter import display_image_in_notebook

if TYPE_CHECKING:
    from notte_sdk.client import AsyncNotteClient, NotteClient

# Retry configuration constants
CLUSTER_OVERLOAD_RETRY_DELAY = 30  # seconds to wait before retrying on 529 errors
CONSOLE_VIEWER_URL = (
    "https://console.notte.cc/static/viewer?ws=wss://api.notte.cc/sessions/{session_id}/debug/recording?token={token}"
)
_playwright_available = False
_async_playwright_available = False


def _observe_server_owned_dialog(_dialog: Any) -> None:
    """Keep the external CDP client from competing with Notte for native dialogs.

    Playwright automatically handles a JavaScript dialog when no listener is
    registered. Native dialogs are target-global, so that default races the
    Notte browser controller attached to the same target. The backend owns
    dialog handling; this listener makes the SDK Playwright connection an
    observer without issuing a second ``Page.handleJavaScriptDialog`` command.
    """


def _install_server_owned_dialog_policy(browser: Any) -> None:
    for context in browser.contexts:
        context.on("dialog", _observe_server_owned_dialog)


try:
    from playwright.sync_api import Browser as BrowserSync
    from playwright.sync_api import Page as PageSync
    from playwright.sync_api import Playwright as PlaywrightSync
    from playwright.sync_api import sync_playwright as _sync_playwright

    _playwright_available = True
except ImportError:
    _sync_playwright = None

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
class SessionsClient(SessionsOperations):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    SESSION_START = "start"
    SESSION_STOP = "{session_id}/stop"
    SESSION_STATUS = "{session_id}"
    SESSION_LIST = ""
    SESSION_VIEWER = "viewer"

    # upload cookies
    SESSION_SET_COOKIES = "{session_id}/cookies"
    SESSION_GET_COOKIES = "{session_id}/cookies"
    # Session Debug
    SESSION_DEBUG = "{session_id}/debug"
    SESSION_DEBUG_TAB = "{session_id}/debug/tab"
    SESSION_DEBUG_REPLAY = "{session_id}/replay"
    SESSION_DEBUG_OFFSET = "{session_id}/offset"

    def __init__(
        self,
        root_client: "NotteClient",
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
        viewer_type: SessionViewerType = SessionViewerType.BROWSER,
    ):
        """
        Initialize a SessionsClient instance.

        Initializes the client with an optional API key and server URL for session management,
        setting the base endpoint to "sessions". Also initializes the last session response to None.
        """
        super().__init__(
            root_client=root_client,
            base_endpoint_path="sessions",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )
        self.page: PageClient = PageClient(
            root_client=root_client, api_key=api_key, verbose=verbose, server_url=server_url
        )
        self.viewer_type: SessionViewerType = viewer_type

    # Legacy: GET debug/tab is absent from the committed OpenAPI schema.
    @staticmethod
    def _session_debug_tab_endpoint(
        session_id: str | None = None, params: TabSessionDebugRequest | None = None
    ) -> NotteEndpoint[TabSessionDebugResponse]:
        """
        Returns an endpoint for retrieving debug information for a session tab.

        If a session ID is provided, it is substituted in the URL path.
        Additional query parameters can be specified via the params argument.

        Returns:
            NotteEndpoint[TabSessionDebugResponse]: The configured endpoint for a GET request.
        """
        path = SessionsClient.SESSION_DEBUG_TAB
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(
            path=path,
            response=TabSessionDebugResponse,
            method="GET",
            params=params,
        )

    @override
    def stop(self, session_id: str, **data: Unpack[SessionStopRequestDict]) -> SessionResponse:
        """
        Stops an active session.

        This method sends a request to the session stop endpoint using the specified
        session ID or the currently active session. It validates the server response,
        clears the internal session state, and returns the validated response.

        Parameters:
            session_id (str, optional): The identifier of the session to close. If not
                provided, the active session ID is used. Raises ValueError if no active
                session exists.

        Returns:
            SessionResponse: The validated response from the session stop request.
        """
        logger.info(f"[Session] {session_id} is stopping")
        return _checked_stop(session_id, super().stop(session_id, **data))

    @override
    def set_cookies(
        self,
        session_id: str,
        cookies: list[CookieDict] | list[Cookie] | None = None,
        cookie_file: str | Path | None = None,
        **data: Any,
    ) -> SetCookiesResponse:
        """
        Uploads cookies to the session.

        Accepts either cookies or cookie_file as argument.

        Args:
            cookies: The list of cookies (can be obtained from session.get_cookies)
            cookie_file: The path to the cookie file (json format)

        Returns:
            SetCookiesResponse: The response from the upload cookies request.
        """
        return super().set_cookies(session_id, cookies=_cookies_to_set(cookies, cookie_file), **data)

    @track_usage("cloud.session.debug.tab")
    def debug_tab_info(self, session_id: str, tab_idx: int | None = None) -> TabSessionDebugResponse:
        """
        Retrieves debug information for a specific tab in the current session.

        If no session ID is provided, the active session is used. If a tab index is provided, the
        debug request is scoped to that tab.

        Parameters:
            session_id (str, optional): The session identifier to use.
            tab_idx (int, optional): The index of the tab for which to retrieve debug info.

        Returns:
            TabSessionDebugResponse: The response containing debug information for the specified tab.
        """
        return self.request(_debug_tab_endpoint(session_id, tab_idx))

    @override
    @track_usage("cloud.session.replay")
    def replay(
        self,
        session_id: str,
        wait: bool = True,
        timeout: float = 240.0,
        poll_interval: float = 5.0,
        *,
        _session_closed: Callable[[], bool] | None = None,
    ) -> ReplayResponse:
        """
        Get presigned URLs for session replay.

        Args:
            session_id: The identifier of the session to get the replay for.
            wait: If True (default), poll until the replay is ready instead of
                raising on 404.
            timeout: Maximum seconds to wait for the replay to become available.
            poll_interval: Seconds between polling attempts.

        Returns:
            ReplayResponse: Presigned URLs for HLS playlist and MP4 download.

        Raises:
            NotteAPIError: If the replay is not found and ``wait`` is False, or
                if the timeout is exceeded.
            TimeoutError: If the replay does not become available within ``timeout`` seconds.
        """
        return run(self, _replay_flow(session_id, wait, timeout, poll_interval, _session_closed))

    @track_usage("cloud.session.viewer.browser")
    def viewer_browser(self, session_id: str, _viewer_url: str | None) -> None:
        """
        Opens live session replay in browser (frame by frame)
        """
        if _viewer_url is None:
            _viewer_url = _require_viewer_url(self.status(session_id=session_id).viewer_url)
        _ = open_browser(_viewer_url, new=1)

    @track_usage("cloud.session.viewer.notebook")
    def viewer_notebook(self, session_id: str) -> WebsocketService:
        """
        Returns a WebsocketJupyterDisplay for displaying live session replay in Jupyter notebook.
        """
        debug_info = self.debug_info(session_id=session_id)
        return WebsocketService(
            wss_url=self._with_db_preview(debug_info.ws.recording), process=display_image_in_notebook
        )

    @track_usage("cloud.session.viewer.cdp")
    def viewer_cdp(self, session_id: str) -> None:
        """
        Opens a browser tab with the debug URL for visualizing the session.

        Retrieves debug information for the specified session and opens
        its debug URL in the default web browser.

        Args:
            session_id (str, optional): The session identifier to use.
                If not provided, the current session ID is used.

        Returns:
            None
        """
        debug_info = self.debug_info(session_id=session_id)
        # open browser tab with debug_url
        _ = open_browser(debug_info.debug_url)

    @track_usage("cloud.session.viewer")
    def viewer(self, session_id: str, _viewer_url: str | None = None) -> None:
        """
        Open the viewer for the session based on the viewer_type.
        """
        match self.viewer_type:
            case SessionViewerType.BROWSER:
                self.viewer_browser(session_id=session_id, _viewer_url=_viewer_url)
            case SessionViewerType.JUPYTER:
                _ = self.viewer_notebook(session_id=session_id)
            case SessionViewerType.CDP:
                self.viewer_cdp(session_id=session_id)


# #######################################################################
# Shared by the sync and async sessions. The flows (see `notte_sdk._flow`) hold
# every polling and retry decision; `SessionsClient` / `RemoteSession` run them
# with blocking calls, `AsyncSessionsClient` / `AsyncRemoteSession` await them.
# #######################################################################


def _checked_stop(session_id: str, response: SessionResponse) -> SessionResponse:
    """The stop response, unless the session did not close."""
    if response.status != "closed":
        raise RuntimeError(f"[Session] {session_id} failed to stop")
    logger.info(f"[Session] {session_id} stopped")
    return response


def _cookies_to_set(
    cookies: list[CookieDict] | list[Cookie] | None, cookie_file: str | Path | None
) -> list[CookieDict] | list[Cookie]:
    """The cookies `set_cookies` sends: `cookies`, or those read from `cookie_file`."""
    if cookies is not None and cookie_file is not None:
        raise ValueError("Cannot provide both cookies and cookie_file")
    if cookie_file is not None:
        cookies = SetCookiesRequest.from_json(cookie_file).cookies
    if cookies is None:
        raise ValueError("Have to provide either cookies or cookie_file")
    return cookies


def _debug_tab_endpoint(session_id: str, tab_idx: int | None) -> NotteEndpoint[TabSessionDebugResponse]:
    params = TabSessionDebugRequest(tab_idx=tab_idx) if tab_idx is not None else None
    return SessionsClient._session_debug_tab_endpoint(session_id=session_id, params=params)  # pyright: ignore [reportPrivateUsage]


def _replay_flow(
    session_id: str, wait: bool, timeout: float, poll_interval: float, session_closed: Callable[[], bool] | None
) -> Flow[ReplayResponse]:
    """`replay`: get the replay, polling until it is ready with `wait`."""
    endpoint = api.session_replay(session_id)
    if not wait:
        return (yield Call("request", (endpoint,)))

    logger.info(f"Waiting for replay of session {session_id} to be ready (timeout={timeout}s)...")
    deadline = time.monotonic() + timeout
    while True:
        try:
            response = yield Call("request", (endpoint,))
            logger.info(f"Replay for session {session_id} is ready")
            return response
        except NotteAPIError as e:
            if e.status_code != 404:
                raise
            waiting_for_close = e.error.get("replay_status") == "waiting_for_session"
            if e.error.get("replay_status") == "disabled" or (
                e.error.get("retryable") is False and not waiting_for_close
            ):
                raise
            error_msg = e.error.get("message", "") or e.error.get("detail", "")
            # The replay service can lag behind a successful stop response
            # while background cleanup persists the session and video.
            if (waiting_for_close or "still active" in error_msg) and not (
                session_closed is not None and session_closed()
            ):
                raise ValueError(
                    f"Session {session_id} is still active — close the session first to generate the replay."
                ) from e
            if time.monotonic() + poll_interval > deadline:
                raise TimeoutError(f"Replay for session {session_id} not ready within {timeout}s") from e
            yield Sleep(poll_interval)


def _require_viewer_url(viewer_url: str | None) -> str:
    if viewer_url is None:
        raise ValueError("Viewer URL is not available. Session might be stopped.")
    return viewer_url


def _start_flow(
    client: "SessionsClient | AsyncSessionsClient", request: SessionStartRequest, tries: int
) -> Flow[SessionResponse | None]:
    """`start`: create the session, retrying server errors the transport did not retry."""
    if request.auth_ids:
        tries = 1  # A timed-out create may already have submitted credentials.
    orig_tries = tries
    while tries > 0:
        tries -= 1
        try:
            response = yield Call("start", kwargs=request.model_dump())
            return response
        except NotteAPIError as e:
            # retry if 5XX error
            status: int | None = e.error.get("status")

            # raise if no tries left
            if tries == 0:
                raise

            # raise if error is a 4XX or status is unknown
            if status is None or 400 <= status < 500:
                raise

            if client.max_retries > 0 and is_retryable_status(status, "POST"):
                raise

            # on 529: cluster overload, retry with backoff
            retry_str = f"{orig_tries - tries}/{orig_tries - 1}"
            if status == 529:
                logger.warning(
                    f"Failed to start session due to cluster overload, retrying in {CLUSTER_OVERLOAD_RETRY_DELAY} seconds ({retry_str})..."
                )
                yield Sleep(CLUSTER_OVERLOAD_RETRY_DELAY)
            else:
                logger.warning(f"Failed to start session: retrying ({retry_str})")
    return None


def _auth_flow(session_id: str, timeout: float) -> Flow[SessionResponse]:
    """`wait_for_auth`: poll authentication readiness, then return the active session's status."""
    deadline = time.monotonic() + timeout
    errors = 0
    while time.monotonic() < deadline:
        try:
            result = yield Call("auth_readiness", (session_id,))
            if result.status == "active":
                result = yield Call("status", (session_id,))
                if result.status == "active":
                    return result
            errors = 0
        except (TransportError, NotteAPIError) as exc:
            if isinstance(exc, NotteAPIError) and 400 <= (exc.error.get("status") or 0) < 500:
                raise
            errors += 1
            if errors >= 3:
                raise
            yield Sleep(1)
            continue
        if result.status != "authenticating":
            raise RuntimeError(result.error or "Session authentication failed")
        yield Sleep(random.uniform(0.8, 1.2))
    raise TimeoutError("Timed out waiting for session authentication")


async def _finish(task: "asyncio.Task[None]") -> bool:
    """Wait until `task` is done; cancelling the waiter does not cancel or abandon the task.

    Returns whether the waiter was cancelled meanwhile.
    """
    cancelled = False
    while not task.done():
        try:
            _ = await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
    return cancelled


def _has_session(session: "RemoteSession | AsyncRemoteSession") -> bool:
    """Whether the session object already stands for a remote session: started, or attached by id."""
    if session.response is not None:
        return True
    return isinstance(session, AsyncRemoteSession) and session._attached_id is not None  # pyright: ignore [reportPrivateUsage]


async def _guarded_entry(
    session: "RemoteSession | AsyncRemoteSession",
    *,
    start: Callable[[], Coroutine[Any, Any, None]],
    wait_for_auth: Callable[[], Awaitable[None]],
    stop: Callable[[], Coroutine[Any, Any, None]],
) -> None:
    """`async with` entry: start, then wait for authentication; a session started meanwhile is stopped
    if the entry fails or is cancelled, since the context manager never exits then."""
    # Only a session this entry creates is stopped: entering an already started or attached
    # session is rejected by `start`, and must not close a browser someone else is using.
    created_here = not _has_session(session)
    start_task = asyncio.create_task(start())
    try:
        # Cancellation does not stop the start: it can still create the session.
        await asyncio.shield(start_task)
        if session.request.wait_for_authentication:
            await wait_for_auth()
    except BaseException:
        # Let the start finish, whether it succeeds or fails: it may have created the session
        # before failing (a cookie file or upload error), and that session must still be stopped.
        # Another cancellation must not abandon the start, nor the stop below.
        _ = await _finish(start_task)
        # A session the start already stopped itself (a failed authentication wait) is closed:
        # no second stop request. The same rule as `RemoteSession.__enter__`.
        if created_here and session.response is not None and session.response.status != "closed":
            stop_task = asyncio.create_task(stop())
            _ = await _finish(stop_task)
            if not stop_task.cancelled() and (stop_error := stop_task.exception()) is not None:
                logger.error(f"Could not clean up session after a failed or cancelled entry: {stop_error}")
        raise


async def _close_async_playwright(session: "RemoteSession | AsyncRemoteSession") -> None:
    """Close the async Playwright browser, then stop its driver. A failure is logged, not raised,
    and does not skip the other step: a failed browser close must not leak the driver process.
    Each handle is dropped only once its close was attempted."""
    if session._async_playwright_browser is not None:  # pyright: ignore [reportPrivateUsage]
        try:
            await session._async_playwright_browser.close()  # pyright: ignore [reportPrivateUsage]
        except Exception as close_error:
            logger.error(f"Failed to close the Playwright browser: {close_error}")
        session._async_playwright_browser = None  # pyright: ignore [reportPrivateUsage]
    session._async_playwright_page = None  # pyright: ignore [reportPrivateUsage]
    if session._async_playwright_context is not None:  # pyright: ignore [reportPrivateUsage]
        try:
            await session._async_playwright_context.stop()  # pyright: ignore [reportPrivateUsage]
        except Exception as stop_error:
            logger.error(f"Failed to stop the Playwright driver: {stop_error}")
        session._async_playwright_context = None  # pyright: ignore [reportPrivateUsage]


async def _async_exit(
    session: "RemoteSession | AsyncRemoteSession",
    exc_val: BaseException | None,
    stop: Callable[[Literal["manual", "error"]], Awaitable[None]],
) -> None:
    """`async with` exit: close the async Playwright connection, then stop the session."""
    if exc_val is not None:
        logger.warning(f"Session exiting because of exception: {exc_val}")

    async def cleanup() -> None:
        # Clean up async playwright resources. A dead local driver must not keep the remote browser
        # running, nor replace the block's own exception: it is logged and the session stopped anyway.
        await _close_async_playwright(session)
        await stop("error" if exc_val is not None else "manual")

    # One task, waited for through cancellations: a cancel must not cut the cleanup short and
    # leave the driver or the remote browser running. It is honoured once the cleanup is done.
    cleanup_task = asyncio.create_task(cleanup())
    cancelled = await _finish(cleanup_task)
    if not cleanup_task.cancelled() and (stop_error := cleanup_task.exception()) is not None:
        if exc_val is None:
            raise stop_error
        logger.error(f"Failed to stop session after async context manager exception: {stop_error}")

    if isinstance(exc_val, KeyboardInterrupt):
        raise KeyboardInterrupt() from None
    if cancelled and exc_val is None:
        raise asyncio.CancelledError()


def _forget_stopped_session(session: "RemoteSession | AsyncRemoteSession") -> None:
    """Drop the state of the session `reset` stopped, so `start` creates a new one.

    The async Playwright driver stays for the next page; the browser and page it connected to
    belonged to the stopped session.
    """
    session.response = None
    session._async_playwright_browser = None  # pyright: ignore [reportPrivateUsage]
    session._async_playwright_page = None  # pyright: ignore [reportPrivateUsage]


def _already_stopped(error: Exception) -> bool:
    return "already stopped" in str(error).lower() or "already closed" in str(error).lower()


def _cookie_dicts(response: GetCookiesResponse) -> list[CookieDict]:
    return [cookie.model_dump() for cookie in response.cookies]  # type: ignore


def _profile_save_data(profile_id: str | None, name: str | None) -> SessionProfileSaveRequestDict:
    """The `save_profile` request for its arguments, which are checked first."""
    if profile_id is not None and name is not None:
        raise ValueError("profile_id and name are mutually exclusive")
    if profile_id is not None and not profile_id.strip():
        raise ValueError("profile_id must not be empty")
    if name is not None and not name.strip():
        raise ValueError("name must not be empty")
    data: SessionProfileSaveRequestDict = {}
    if profile_id is not None:
        data["profile_id"] = profile_id
    if name is not None:
        data["name"] = name
    return data


def _known_cdp_url(
    client: "SessionsClient | AsyncSessionsClient", request: SessionStartRequest, response: SessionResponse | None
) -> str | None:
    """The session's CDP url, or None when only `debug_info` knows it."""
    if response is None:
        raise ValueError("You need to start the session first to get the cdp url")
    if request.cdp_url is not None:
        # cdp url from another session provider. It is handed to us by the
        # caller and served by someone else, so it gets no preview selector.
        return request.cdp_url
    # The remaining urls are websocket endpoints on our own API, which reads
    # the preview branch from the query string. Without it the handshake is
    # served from the default database and rejects a preview-branch session.
    if response.cdp_url is not None:
        return client._with_db_preview(response.cdp_url)  # pyright: ignore [reportPrivateUsage]
    return None


def _cdp_headers(
    client: "SessionsClient | AsyncSessionsClient", request: SessionStartRequest, cdp_url: str
) -> dict[str, str] | None:
    """Headers for this API's CDP connection: the SDK identity, and the runner capability if set.

    Nothing is sent to a CDP endpoint served by someone else.
    """
    if request.cdp_url is not None:
        return None
    target = urlsplit(cdp_url)
    api = urlsplit(client.server_url)
    secure = target.scheme == "wss" and api.scheme == "https"
    plain = target.scheme == "ws" and api.scheme == "http"
    default_port = 443 if secure else 80
    target_port = target.port if target.port is not None else default_port
    api_port = api.port if api.port is not None else default_port
    if not ((secure or plain) and target.hostname == api.hostname and target_port == api_port):
        return None
    headers = {"x-notte-request-origin": client.REQUEST_ORIGIN, "x-notte-sdk-version": notte_core_version}
    # The capability is a credential: only ever sent over TLS.
    if secure and (capability := os.getenv("NOTTE_AUTH_CAPABILITY")):
        headers["x-notte-auth-capability"] = capability
    return headers


async def _async_page(
    session: "RemoteSession | AsyncRemoteSession", cdp_url: Callable[[], Awaitable[str]]
) -> "PageAsync":
    """The async Playwright page connected to the session over CDP, connecting on first use."""
    if not _async_playwright_available:
        raise ImportError("Playwright not installed. Use `pip install notte-sdk[playwright]` to install it.")

    # Return cached page if already connected
    if session._async_playwright_page is not None:  # pyright: ignore [reportPrivateUsage]
        return session._async_playwright_page  # pyright: ignore [reportPrivateUsage]

    try:
        # Initialize async playwright context
        if session._async_playwright_context is None:  # pyright: ignore [reportPrivateUsage]
            if _async_playwright is None:
                raise RuntimeError("Playwright is not initialized")
            session._async_playwright_context = await _async_playwright().start()  # pyright: ignore [reportPrivateUsage]

        # Connect to browser via CDP
        if session._async_playwright_browser is None:  # pyright: ignore [reportPrivateUsage]
            url = await cdp_url()
            session._async_playwright_browser = await session._async_playwright_context.chromium.connect_over_cdp(  # pyright: ignore [reportPrivateUsage]
                url,
                headers=session._cdp_headers(url),  # pyright: ignore [reportPrivateUsage]
            )
            _install_server_owned_dialog_policy(session._async_playwright_browser)  # pyright: ignore [reportPrivateUsage]

        # Get the first page from the first context
        session._async_playwright_page = session._async_playwright_browser.contexts[0].pages[0]  # pyright: ignore [reportPrivateUsage]
        return session._async_playwright_page  # pyright: ignore [reportPrivateUsage]
    except Exception as e:
        raise RuntimeError("Failed to access the async playwright page from CDP") from e


def _with_perception(data: ObserveRequestDict, default: PerceptionType) -> ObserveRequestDict:
    """Observe `data`, with the session's default perception type unless one is given."""
    if data.get("perception_type") is None:
        data["perception_type"] = default
    return data


def _action_from(action: BaseAction | None, kwargs: dict[str, Any]) -> BaseAction:
    """The action `execute` runs: `action`, or one built from keyword arguments."""
    # Fast path: if action is already a BaseAction, use it directly
    if isinstance(action, BaseAction):
        return action
    if kwargs:
        if "type" not in kwargs:
            raise ValueError("Missing required action field: 'type'")
        # Convert kwargs to BaseAction using fast mapping
        return action_dict_to_base_action(kwargs)  # type: ignore[arg-type]
    if action is None:
        raise ValueError("No action provided")
    # Fallback for dict (shouldn't happen with new API, but kept for compatibility)
    return ExecutionRequest.get_action(action=action, data=None)  # pyright: ignore [reportUnreachable]


def _checked_execution(
    result: ExecutionResult, action: BaseAction, raise_on_failure: bool | None, default_raise_on_failure: bool
) -> ExecutionResult:
    """`result`, unless the action failed and failures raise."""
    # raise exception if needed
    _raise_on_failure = raise_on_failure if raise_on_failure is not None else default_raise_on_failure
    # Gate on "did the action fail", not "did something throw", to mirror the local session.
    if _raise_on_failure and not result.success:
        logger.error(f"🚨 Execution failed with message: '{result.message}'")
        if result.exception is not None:
            # `ExecutionResult` validation rehydrated the concrete error type, messages
            # and flags from the structured `exception_detail` wire payload.
            raise result.exception
        # An API build that predates `exception_detail` may report a failure without
        # an exception; the message is all the caller has to go on.
        fallback_message = str(result.message).strip() or f"Failed to execute action: {action.type}"
        raise NotteBaseError(
            dev_message=fallback_message,
            user_message=fallback_message,
            agent_message=fallback_message,
        )
    return result


def _evaluated(result: ExecutionResult, raise_on_failure: bool) -> str | ExecutionResult:
    """What `evaluate_js` returns for the `evaluate_js` action's result."""
    if not raise_on_failure:
        return result
    if result.data is None:
        # an API build that predates the eval-js fix reports success without data
        raise EvaluateJsNoDataError()
    return result.data.markdown


class RemoteSession(SyncResource):
    """
    A remote session that can be managed through the Notte API.

    This class provides an interface for starting, stopping, and monitoring sessions.
    It implements the SyncResource interface for resource management and maintains
    state about the current session execution.

    Attributes:
        request (SessionStartRequest): The configuration request used to create this session.
        client (SessionsClient): The client used to communicate with the Notte API.
        response (SessionResponse | None): The latest response from the session execution.
    """

    @overload
    def __init__(
        self,
        *,
        storage: RemoteFileStorage | None = None,
        perception_type: PerceptionType = "fast",
        raise_on_failure: bool = config.raise_on_session_execution_failure,
        cookie_file: str | Path | None = None,
        open_viewer: bool = False,
        _client: SessionsClient | None = None,
        **data: Unpack[SessionStartRequestDict],
    ) -> None: ...

    @overload
    def __init__(self, /, session_id: str, *, _client: SessionsClient | None = None) -> None: ...

    def __init__(
        self,
        session_id: str | None = None,
        *,
        storage: RemoteFileStorage | None = None,
        perception_type: PerceptionType = "fast",
        cookie_file: str | Path | None = None,
        raise_on_failure: bool = config.raise_on_session_execution_failure,
        open_viewer: bool = False,
        _client: SessionsClient | None = None,
        **data: Unpack[SessionStartRequestDict],
    ) -> None:
        """
        Create a new RemoteSession instance with the specified configuration.

        This method validates the session creation request and returns a new
        RemoteSession instance configured with the specified parameters.

        Args:
            storage: File Storage to attach to the session
            perception_type: Default perception type for `observe()`. Defaults to `'fast'`. `'deep'` is deprecated and removed on December 1, 2026; use `'fast'`.
            open_viewer: Whether to open the live viewer when the session starts (default: False).
                This controls only the viewer popup and is independent of the browser environment.
            advanced_stealth: Enable Notte's highest-fidelity browser environment. Available to approved workspaces.
            wait_for_authentication: Defaults to True. The SDK waits for authentication readiness through short API calls before returning from start or entering a context manager. When False, start returns after inline verification; call wait_for_auth() or await_for_auth() before browser actions if login is pending.
            **data: Keyword arguments for the session creation request.

        Returns:
            RemoteSession: A new RemoteSession instance configured with the specified parameters.
        """
        if _client is None:
            raise ValueError("SessionsClient is required")

        # Filter out open_viewer from data before validating with SessionStartRequest
        # (open_viewer is a RemoteSession parameter, not a SessionStartRequest field)
        request_data = {k: v for k, v in data.items() if k != "open_viewer"}
        request = SessionStartRequest.from_data(request_data)

        response: SessionResponse | None = None
        if session_id is not None:
            response = _client.status(session_id=session_id)
        # init attributes
        self.request: SessionStartRequest = request
        self._open_viewer: bool = open_viewer

        self.client: SessionsClient = _client
        self.response: SessionResponse | None = response
        self.storage: RemoteFileStorage = storage or RemoteFileStorage(_client=_client.root_client.files)
        if session_id is not None:
            self.storage = self.storage.for_session(session_id)
        self.default_perception_type: PerceptionType = perception_type
        self.default_raise_on_failure: bool = raise_on_failure
        self._cookie_file: Path | None = Path(cookie_file) if cookie_file is not None else None
        # Sync playwright instances
        self._playwright_context: "PlaywrightSync | None" = None
        self._playwright_browser: "BrowserSync | None" = None
        self._playwright_page: Any | None = None
        # Async playwright instances
        self._async_playwright_context: "PlaywrightAsync | None" = None
        self._async_playwright_browser: "BrowserAsync | None" = None
        self._async_playwright_page: "PageAsync | None" = None

    @override
    def __enter__(self) -> Self:  # pyright: ignore [reportMissingSuperCall]
        """
        Context manager entry point: starts the session.

        If the entry fails after the session was created (an invalid cookie file, a failed cookie
        upload or an interrupt), the session is stopped before the error is raised, since the
        context manager never exits then.

        Returns:
            RemoteSession: The session instance.
        """
        created = self.response is None
        try:
            self.start()
        except BaseException:
            # A failed authentication wait already stopped the session.
            if created and self.response is not None and self.response.status != "closed":
                try:
                    self.stop(close_reason="error")
                except Exception as stop_error:
                    logger.error(f"Failed to stop session after context manager entry failed: {stop_error}")
            raise
        return self

    @override
    def __exit__(  # pyright: ignore [reportMissingSuperCall]
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        if exc_val is not None:
            logger.warning(f"Session exiting because of exception: {exc_val}")

        # Clean up sync playwright resources. A dead local driver must not keep the remote browser
        # running, nor replace the block's own exception: log it and stop the session anyway.
        # The browser and the driver are closed separately: a failed close must not leak the driver.
        if self._playwright_browser is not None:
            try:
                self._playwright_browser.close()
            except Exception as close_error:
                logger.error(f"Failed to close the Playwright browser: {close_error}")
        if self._playwright_context is not None:
            try:
                self._playwright_context.stop()
            except Exception as stop_error:
                logger.error(f"Failed to stop the Playwright driver: {stop_error}")
        self._playwright_browser = None
        self._playwright_context = None
        self._playwright_page = None

        try:
            self.stop(close_reason="error" if exc_val is not None else "manual")
        except Exception as stop_error:
            if exc_val is None:
                raise
            logger.error(f"Failed to stop session after context manager exception: {stop_error}")

        if isinstance(exc_val, KeyboardInterrupt):
            raise KeyboardInterrupt() from None

    async def __aenter__(self) -> "RemoteSession":
        """
        Async context manager entry point.

        Returns:
            RemoteSession: The session instance.
        """
        await _guarded_entry(
            self,
            start=lambda: asyncio.to_thread(self.start, wait_for_authentication=False),
            wait_for_auth=lambda: self.await_for_auth(),
            stop=lambda: asyncio.to_thread(self.stop, close_reason="error"),
        )
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        """
        Async context manager exit point with cleanup of async playwright resources.
        """

        async def stop(close_reason: Literal["manual", "error"]) -> None:
            # A blocking stop (cookie saving, the stop request) runs off the event loop.
            await asyncio.to_thread(self.stop, close_reason=close_reason)

        await _async_exit(self, exc_val, stop)

    # #######################################################################
    # ############################# Session #################################
    # #######################################################################

    @override
    def start(self, tries: int = 3, *, wait_for_authentication: bool | None = None) -> None:
        """
        Start the session using the configured request.

        This method sends a start request to the API and logs the session ID
        upon successful start.

        **Example:**

        ```python
        from notte_sdk import NotteClient

        client = NotteClient()
        session = client.Session()
        session.start()
        ```

        > Note that we strongly recommend using the `with` statement to start and stop the session to avoid any issues with session cleanup.

        **Example:**
        ```python
        from notte_sdk import NotteClient

        client = NotteClient()
        with client.Session() as session:
            session.execute(type="goto", url="https://www.notte.cc")
        ```

        Raises:
            ValueError: If the session request is invalid.
        """
        if self.response is not None:
            raise ValueError("Session already started")

        self.response = run(self.client, _start_flow(self.client, self.request, tries))
        self.storage = self.storage.for_session(self.session_id)

        logger.info(f"[Session] {self.session_id} started")
        should_wait = (
            self.request.wait_for_authentication if wait_for_authentication is None else wait_for_authentication
        )
        if should_wait:
            try:
                self.wait_for_auth()
            except BaseException:
                self.stop(close_reason="error")
                raise

        if self._open_viewer:
            self.viewer()
        # try to load cookies from file
        if self._cookie_file is not None:
            if Path(self._cookie_file).exists():
                logger.info(f"🍪 Automatically loading cookies from {self._cookie_file}")
                _ = self.set_cookies(cookie_file=self._cookie_file)
            else:
                logger.warning(f"🍪 Cookie file {self._cookie_file} not found, skipping cookie loading")

    def wait_for_auth(self, timeout: float = 615) -> None:
        """Wait for this browser to be ready without restarting or relogging it."""
        if self.response is None:
            raise ValueError("Session has not started")
        if self.response.status == "active":
            return
        self.response = run(self.client, _auth_flow(self.response.session_id, timeout))

    async def await_for_auth(self, timeout: float = 615) -> None:
        """Async readiness wait; blocking HTTP calls run outside the event loop."""
        if self.response is None:
            raise ValueError("Session has not started")
        if self.response.status == "active":
            return
        self.response = await arun(self.client, _auth_flow(self.response.session_id, timeout), in_thread=True)

    @override
    def stop(self, close_reason: Literal["manual", "error"] = "manual") -> None:
        """
        Stop the session and clean up resources.

        This method sends a close request to the API and verifies that the session
        was properly closed. It logs the session closure and raises an error if
        the session fails to close.

        **Example:**
        ```python
        from notte_sdk import NotteClient

        client = NotteClient()
        session = client.Session()
        session.start()
        session.stop()
        ```

        > Note that we strongly recommend using the `with` statement to start and stop the session to avoid any issues with session cleanup.

        **Example:**
        ```python
        from notte_sdk import NotteClient

        client = NotteClient()
        with client.Session() as session:
            session.execute(type="goto", url="https://www.notte.cc")
        ```

        Raises:
            ValueError: If the session hasn't been started (no session_id available).
            RuntimeError: If the session fails to close properly.
        """
        if self._cookie_file is not None:
            try:
                cookies = self.get_cookies()
                create_or_append_cookies_to_file(self._cookie_file, cookies)
            except Exception as e:
                logger.error(f"🍪 Error saving cookies to {self._cookie_file}: {e}")
        try:
            self.response = self.client.stop(session_id=self.session_id, close_reason=close_reason)
        except Exception as e:
            if _already_stopped(e):
                logger.warning(f"Session {self.session_id} was already stopped")
            else:
                raise

    @override
    def reset(self) -> None:
        """
        Stop the session, then start a new one with the same configuration.

        The new session has a new session ID. A Playwright page must be opened again.
        """
        self.stop()
        _forget_stopped_session(self)
        # The sync Playwright driver stays for the next page, like the async one.
        self._playwright_browser = None
        self._playwright_page = None
        self.start()

    @property
    def session_id(self) -> str:
        """
        Get the ID of the current session.

        Returns:
            str: The unique identifier of the current session.

        Raises:
            ValueError: If the session hasn't been started yet (no response available).
        """
        if self.response is None:
            raise ValueError("You need to start the session first to get the session id")
        return self.response.session_id

    def offset(self) -> int:
        """
        Get the trajectory offset of the session

        This is useful to start an agent that remembers information about steps
        that happened before it started.

        **Example:**
        ```python
        offset = session.offset()
        ```

        Returns:
            int: The session trajectory offset

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        return self.client.offset(session_id=self.session_id).offset

    def replay(
        self,
        wait: bool = True,
        timeout: float = 240.0,
        poll_interval: float = 5.0,
    ) -> ReplayResponse:
        """
        Get presigned URLs for the session replay.

        **Example:**
        ```python
        replay = session.replay()
        print(replay.mp4_url)  # Presigned URL for MP4 download
        replay.download("session.mp4")
        ```

        By default this polls until the replay is ready. Set ``wait=False``
        to fail immediately if the replay is not yet available.

        Args:
            wait: If True (default), poll until the replay is ready.
            timeout: Maximum seconds to wait (default 240).
            poll_interval: Seconds between polling attempts (default 5).

        Returns:
            ReplayResponse: Presigned URLs for HLS playlist and MP4 download.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
            TimeoutError: If the replay does not become available within ``timeout`` seconds.
        """
        return self.client.replay(
            session_id=self.session_id,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
            _session_closed=lambda: self.response is not None and self.response.status == "closed",
        )

    def viewer_browser(self) -> None:
        """
        Opens live session replay in browser (frame by frame) in a new browser tab.

        **Example:**
        ```python
        session.viewer_browser()
        ```
        """
        _viewer_url = self.response.viewer_url if self.response is not None else None
        return self.client.viewer_browser(self.session_id, _viewer_url=_viewer_url)

    def viewer_notebook(self) -> WebsocketService:
        """
        Returns a WebsocketJupyterDisplay for displaying live session replay in Jupyter notebook.

        Use this method in a Jupyter notebook to display the session replay in a cell.

        ```python
        session.viewer_notebook()
        ```
        """
        return self.client.viewer_notebook(session_id=self.session_id)

    def viewer_cdp(self) -> None:
        """
        Open a browser tab with the debug URL for visualizing the session.

        This method opens the default web browser to display the session's debug interface.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        self.client.viewer_cdp(session_id=self.session_id)

    def viewer(self) -> None:
        """
        Open the viewer for the session based on the viewer_type.
        """
        match self.client.viewer_type:
            case SessionViewerType.BROWSER:
                self.viewer_browser()
            case SessionViewerType.JUPYTER:
                _ = self.viewer_notebook()
            case SessionViewerType.CDP:
                self.viewer_cdp()

    def status(self) -> SessionResponse:
        """
        Get the current status of the session.

        This method is useful if you want to check if the current session is active or not (or when it has been started/stopped).

        **Example:**
        ```python
        status = session.status()
        ```

        Returns:
            SessionResponse: The current status information of the session.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        return self.client.status(session_id=self.session_id)

    def set_cookies(
        self,
        cookies: list[CookieDict] | None = None,
        cookie_file: str | Path | None = None,
    ) -> SetCookiesResponse:
        """
        Uploads cookies to the session.

        import UploadCookiesSimple from '/snippets/sessions/upload_cookies_simple.mdx';

        Accepts either cookies (list of dicts) or cookie_file (json file path) as argument.

        <UploadCookiesSimple />

        Args:
            cookies: The list of cookies (can be obtained from session.get_cookies)
            cookie_file: The path to the cookie file (json format)

        Returns:
            SetCookiesResponse: The response from the upload cookies request.

        Raises:
            ValueError: If both cookies and cookie_file are provided, or if neither is provided.
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        return self.client.set_cookies(session_id=self.session_id, cookies=cookies, cookie_file=cookie_file)

    def get_cookies(self) -> list[CookieDict]:
        """
        Gets cookies from the session.

        ```python
        import json
        cookies = session.get_cookies() # get the cookies from the session
        with open("cookies.json", "w") as f:
            json.dump(cookies, f) # save the cookies to a json file
        ```

        Returns:
            GetCookiesResponse: The response containing the list of cookies in the session.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        return _cookie_dicts(self.client.get_cookies(session_id=self.session_id))

    def save_profile(self, profile_id: str | None = None, name: str | None = None) -> ProfileResponse:
        """
        Saves the session's current browser state into a profile, without stopping the session.

        See [Browser Profiles](/features/sessions/browser-profiles) for the tested Python and TypeScript example.

        Use it to keep a login from a session that was started without ``persist=True``.
        It does not change the session's start-time profile settings, so a session started
        with ``persist=True`` still saves again when it stops.

        Args:
            profile_id: Existing profile to overwrite with the current browser state.
            name: Create a new profile with this name and save into it. Mutually exclusive with ``profile_id``.
                With neither, the state is saved into the profile the session was started with.

        Returns:
            ProfileResponse: The profile, with ``persisted_domains`` computed from the saved state.

        Raises:
            ValueError: If both ``profile_id`` and ``name`` are provided, or if either is empty.
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        data = _profile_save_data(profile_id, name)
        return self.client.save_profile(session_id=self.session_id, **data)

    def debug_info(self) -> SessionDebugResponse:
        """
        Get detailed debug information for the session.

        Returns:
            SessionDebugResponse: Debug information for the session.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        return self.client.debug_info(session_id=self.session_id)

    def cdp_url(self) -> str:
        """
        Get the Chrome DevTools Protocol WebSocket URL for the session.

        import CDPPlaywright from '/snippets/sessions/cdp.mdx';

        This URL can be used to connect to the browser's debugging interface.

        Here is an example how to connect to playwright using the notte session cdp url:

        <CDPPlaywright />

        Returns:
            str: The WebSocket URL for the Chrome DevTools Protocol.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        if (known := _known_cdp_url(self.client, self.request, self.response)) is not None:
            return known
        # cdp url from the session provider
        return self.client._with_db_preview(self.debug_info().ws.cdp)  # pyright: ignore [reportPrivateUsage]

    def _cdp_headers(self, cdp_url: str) -> dict[str, str] | None:
        """Headers for this API's CDP connection: the SDK identity, and the runner capability if set.

        Nothing is sent to a CDP endpoint served by someone else.
        """
        return _cdp_headers(self.client, self.request, cdp_url)

    @property
    def page(self) -> "PageSync":
        """
        Get a Playwright page connected to the session via CDP.

        This property provides direct access to the browser page using Playwright's API.
        The connection is established lazily on first access and cached for subsequent calls.

        **Example:**
        ```python
        from notte_sdk import NotteClient

        client = NotteClient()
        with client.Session() as session:
            # Access the playwright page
            page = session.page
            page.goto("https://www.google.com")
            screenshot = page.screenshot(path="screenshot.png")
        ```

        Returns:
            PlaywrightPage: A Playwright page instance connected to the session.

        Raises:
            ImportError: If playwright is not installed. Install with `pip install notte-sdk[playwright]`
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        if not _playwright_available:
            raise ImportError("Playwright not installed. Use `pip install notte-sdk[playwright]` to install it.")

        # Return cached page if already connected
        if self._playwright_page is not None:
            return self._playwright_page

        if self._async_playwright_page is not None:
            raise RuntimeError(
                "Session Page has been initialized with async playwright. Use `await session.apage()` instead."
            )
        try:
            # Initialize playwright context
            if self._playwright_context is None:
                if _sync_playwright is None:
                    raise RuntimeError("Playwright is not initialized")
                self._playwright_context = _sync_playwright().start()

            # Connect to browser via CDP
            if self._playwright_browser is None:
                cdp_url = self.cdp_url()
                self._playwright_browser = self._playwright_context.chromium.connect_over_cdp(
                    cdp_url, headers=self._cdp_headers(cdp_url)
                )
                _install_server_owned_dialog_policy(self._playwright_browser)

            # Get the first page from the first context
            self._playwright_page = self._playwright_browser.contexts[0].pages[0]
            return self._playwright_page
        except Exception as e:
            raise RuntimeError("Failed to access the playwright page from CDP") from e

    @property
    async def apage(self) -> "PageAsync":
        """
        Get an async Playwright page connected to the session via CDP.

        This method provides direct access to the browser page using Playwright's async API.
        The connection is established lazily on first access and cached for subsequent calls.

        **Example:**
        ```python
        from notte_sdk import NotteClient

        client = NotteClient()
        async with client.Session() as session:
            # Access the async playwright page
            page = await session.apage()
            await page.goto("https://www.google.com")
            screenshot = await page.screenshot(path="screenshot.png")
        ```

        Returns:
            PlaywrightPage: An async Playwright page instance connected to the session.

        Raises:
            ImportError: If playwright is not installed. Install with `pip install notte-sdk[playwright]`
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        if _async_playwright_available and self._async_playwright_page is None and self._playwright_browser is not None:
            raise RuntimeError("Session Page has been initialized with sync playwright. Use `session.page` instead.")

        async def cdp_url() -> str:
            return self.cdp_url()

        return await _async_page(self, cdp_url)

    # #######################################################################
    # ############################# PAGE ####################################
    # #######################################################################

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
        self, *, raise_on_failure: bool = True, **data: Unpack[ScrapeRequestDict]
    ) -> StructuredData[BaseModel] | BaseModel | dict[str, Any] | str:
        """
        Scrape the current page data.

        This endpoint is a wrapper around the `session.scrape` method that automatically starts a new session, goes to the given URL, and scrapes the page.

        **Example:**
        ```python
        from notte_sdk import NotteClient

        client = NotteClient()
        with client.Session() as session:
            session.execute(type="goto", url="https://www.google.com")
            markdown = session.scrape(only_main_content=False)
        ```

        With structured data:
        ```python
        from notte_sdk import NotteClient
        from pydantic import BaseModel

        # Define your Pydantic model
        ...

        client = NotteClient()
        with client.Session() as session:
            session.execute(type="goto", url="https://www.notte.cc")
            data = session.scrape(
                response_format=Product,
                instructions="Extract the products names and prices"
            )
        ```


        Args:
            **data: Arbitrary keyword arguments validated against ScrapeRequestDict,

        Returns:
            Extracted data as structured data, markdown text, or a StructuredData wrapper when
            ``raise_on_failure=False``.

        """
        return self.client.page.scrape(self.session_id, raise_on_failure=raise_on_failure, **data)

    @overload
    def observe(
        self,
        *,
        instructions: str,
        url: str | None = None,
        perception_type: PerceptionType | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> list[InteractionActionUnion]: ...

    @overload
    def observe(
        self,
        *,
        instructions: None = None,
        url: str | None = None,
        perception_type: PerceptionType | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> ObserveResponse: ...

    def observe(self, **data: Unpack[ObserveRequestDict]) -> ObserveResponse | list[InteractionActionUnion]:
        """
        Observes the current session page.

        **Observation Response:**
        - a list of actions that can be taken on the page (e.g. click on a button, scroll, etc.)
        - a screenshot of the page (base64 encoded)
        - some metadata about the page (title, url, etc.)

        ```python
        # Observe the page
        obs = session.observe()
        # Select an action from the list of interactible elements on the page
        actions = obs.space.interaction_actions
        # display the action space as a string to be able to visualize it
        print(obs.space.description)
        # get the screenshot
        screenshot = obs.screenshot.bytes()
        # or the same screenshot with the interactive elements outlined and labelled with their ids
        highlighted = obs.screenshot.highlighted()
        ```

        Once you have selected an action (either manually or using an LLM), you can execute it with:
        ```python
        session.execute(action)
        ```

        Deprecated: `perception_type='deep'` and `instructions` are removed on December 1, 2026, and passing
        either emits a `DeprecationWarning`. Use `perception_type='fast'` (the default) instead of `'deep'`.
        For `instructions`: `<<ALTERNATIVE FOR instructions: session.act() — pending>>`. See the migration guide: https://docs.notte.cc/features/sessions/observe-migration


        Args:
            **data: Arbitrary keyword arguments corresponding to observation request fields.

        Returns:
            ObserveResponse: The formatted observation result from the API response when no instructions provided.
            list[InteractionActionUnion]: The filtered list of actions when instructions is provided.
        """
        data = _with_perception(data, self.default_perception_type)
        return self.client.page.observe(session_id=self.session_id, **data)  # pyright: ignore[reportUnknownVariableType, reportArgumentType, reportCallIssue]

    # BEGIN GENERATED OVERLOADS: execute (scripts/generate_action_overloads.py)
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
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[EmailVerificationReadActionDict]
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
    @overload
    def execute(self, action: BaseAction, *, raise_on_failure: bool | None = None) -> ExecutionResult: ...

    # END GENERATED OVERLOADS: execute

    def execute(
        self,
        action: BaseAction | None = None,
        *,
        raise_on_failure: bool | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Executes an action on the current session page.

        This method allows you to interact with web elements by performing various actions
        like clicking, filling forms, navigating, scrolling, and more. You can provide
        actions either as structured action objects or by specifying action parameters directly.

        ```python
        from notte_sdk import actions

        # Execute an action from observe() results
        obs = session.observe()
        action = obs.space.first()  # Get first available action
        result = session.execute(action)

        # Execute a click action by element ID.
        # Pseudo observe output: [B1] button "Submit"
        # Only use IDs that appear in your live observe() output.
        result = session.execute(type="click", id="B1")

        # Execute a fill action by element ID.
        # Pseudo observe output: [I1] input "Email"
        # Only use IDs that appear in your live observe() output.
        result = session.execute(type="fill", id="I1", value="user@example.com")

        # Execute browser navigation
        result = session.execute(type="goto", url="https://example.com")
        ```

        **Action Types:**

        **Browser Actions** (always available):
        - `goto`: Navigate to a URL
        - `go_back`: Go back to previous page
        - `go_forward`: Go forward to next page
        - `reload`: Reload current page
        - `scroll_up`/`scroll_down`: Scroll the page
        - `wait`: Wait for specified milliseconds
        - `press_key`: Press keyboard keys

        **Interaction Actions** (require element ID from observe):
        - `click`: Click on an element
        - `fill`: Fill input fields with text
        - `upload_file`: upload files to file inputs
        - etc.

        Do not write interaction code with guessed element IDs, selectors, or field names.
        Element IDs must come from a live `observe()` call, and selectors/field names should
        be validated against the actual page before they are used in automation.

        **Using Playwright Selectors:**

        Instead of element IDs, you can use Playwright selectors to target elements:

        ```python
        session.execute(type="fill", selector="internal:text=\"Email\"", value="test@example.com")
        ```

        This syntax also supports Xpath (e.g. `xpath=/html/body/div[3]/div/button[1]`) or CSS selectors (e.g. `css=button.submit`).
        > Note that we strongly advice to use selectors over IDs for automations because IDs are dependent on the page structure and can change over time.


        Args:
            raise_on_failure: If true, will raise if we could not execute the action
            **kwargs: Action fields as keyword arguments.

        Returns:
            ExecutionResponseWithSession: Result containing execution details, any errors,
                and the updated session state.

        Raises:
            Exception: If raise_on_failure is True and the action execution fails.
        """
        action_obj = _action_from(action, kwargs)
        result = self.client.page.execute(session_id=self.session_id, action=action_obj)
        return _checked_execution(result, action_obj, raise_on_failure, self.default_raise_on_failure)

    # raise_on_failure=True (default) -> the evaluated string; failures raise
    @overload
    def evaluate_js(self, code: str, *, raise_on_failure: Literal[True] = ...) -> str: ...

    # raise_on_failure=False -> the ExecutionResult envelope, like execute()
    @overload
    def evaluate_js(self, code: str, *, raise_on_failure: Literal[False]) -> ExecutionResult: ...

    def evaluate_js(self, code: str, *, raise_on_failure: bool = True) -> str | ExecutionResult:
        """
        Evaluate JavaScript on the current page and return its result as a string.

        The result is stringified the way `evaluate_js` records it: objects and
        arrays as JSON, a JS `null` as the string `"null"`. On failure the typed
        exception is raised with the actual JavaScript error; pass
        `raise_on_failure=False` to get the `ExecutionResult` envelope instead.

        ```python
        payload = json.loads(session.evaluate_js("(async () => JSON.stringify(await res.json()))()"))
        ```
        """
        return _evaluated(
            self.execute(type="evaluate_js", code=code, raise_on_failure=raise_on_failure), raise_on_failure
        )

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
    ) -> FetchResponse:
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

        ```python
        session.execute(type="goto", url="https://en.wikipedia.org/wiki/Main_Page")
        summary = session.fetch("/api/rest_v1/page/summary/Main_Page").json()
        ```
        """
        script = build_fetch_script(
            url, method=method, headers=headers, params=params, json_body=json, data=data, timeout=timeout
        )
        return response_from_evaluated(self.evaluate_js(script))


@final
class AsyncSessionsClient(AsyncSessionsOperations):
    """The async twin of `SessionsClient`, for `AsyncNotteClient`: the same methods as coroutines."""

    def __init__(
        self,
        root_client: "AsyncNotteClient",
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
        viewer_type: SessionViewerType = SessionViewerType.BROWSER,
    ):
        super().__init__(
            root_client=root_client,
            base_endpoint_path="sessions",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )
        self.page: AsyncPageClient = AsyncPageClient(
            root_client=root_client, api_key=api_key, verbose=verbose, server_url=server_url
        )
        self.viewer_type: SessionViewerType = viewer_type

    @override
    async def stop(self, session_id: str, **data: Unpack[SessionStopRequestDict]) -> SessionResponse:
        """
        Stops an active session.

        This method sends a request to the session stop endpoint using the specified
        session ID or the currently active session. It validates the server response,
        clears the internal session state, and returns the validated response.

        Parameters:
            session_id (str, optional): The identifier of the session to close. If not
                provided, the active session ID is used. Raises ValueError if no active
                session exists.

        Returns:
            SessionResponse: The validated response from the session stop request.
        """
        logger.info(f"[Session] {session_id} is stopping")
        return _checked_stop(session_id, await super().stop(session_id, **data))

    @override
    async def set_cookies(
        self,
        session_id: str,
        cookies: list[CookieDict] | list[Cookie] | None = None,
        cookie_file: str | Path | None = None,
        **data: Any,
    ) -> SetCookiesResponse:
        """
        Uploads cookies to the session.

        Accepts either cookies or cookie_file as argument.

        Args:
            cookies: The list of cookies (can be obtained from session.get_cookies)
            cookie_file: The path to the cookie file (json format)

        Returns:
            SetCookiesResponse: The response from the upload cookies request.
        """
        if cookie_file is not None:
            cookies = await asyncio.to_thread(_cookies_to_set, cookies, cookie_file)
        return await super().set_cookies(session_id, cookies=_cookies_to_set(cookies, None), **data)

    @track_usage("cloud.session.debug.tab")
    async def debug_tab_info(self, session_id: str, tab_idx: int | None = None) -> TabSessionDebugResponse:
        """
        Retrieves debug information for a specific tab in the current session.

        If no session ID is provided, the active session is used. If a tab index is provided, the
        debug request is scoped to that tab.

        Parameters:
            session_id (str, optional): The session identifier to use.
            tab_idx (int, optional): The index of the tab for which to retrieve debug info.

        Returns:
            TabSessionDebugResponse: The response containing debug information for the specified tab.
        """
        return await self.request(_debug_tab_endpoint(session_id, tab_idx))

    @override
    @track_usage("cloud.session.replay")
    async def replay(
        self,
        session_id: str,
        wait: bool = True,
        timeout: float = 240.0,
        poll_interval: float = 5.0,
        *,
        _session_closed: Callable[[], bool] | None = None,
    ) -> ReplayResponse:
        """
        Get presigned URLs for session replay.

        Args:
            session_id: The identifier of the session to get the replay for.
            wait: If True (default), poll until the replay is ready instead of
                raising on 404.
            timeout: Maximum seconds to wait for the replay to become available.
            poll_interval: Seconds between polling attempts.

        Returns:
            ReplayResponse: Presigned URLs for HLS playlist and MP4 download.

        Raises:
            NotteAPIError: If the replay is not found and ``wait`` is False, or
                if the timeout is exceeded.
            TimeoutError: If the replay does not become available within ``timeout`` seconds.
        """
        return await arun(self, _replay_flow(session_id, wait, timeout, poll_interval, _session_closed))

    @track_usage("cloud.session.viewer.browser")
    async def viewer_browser(self, session_id: str, _viewer_url: str | None) -> None:
        """
        Opens live session replay in browser (frame by frame)
        """
        if _viewer_url is None:
            _viewer_url = _require_viewer_url((await self.status(session_id=session_id)).viewer_url)
        _ = await asyncio.to_thread(open_browser, _viewer_url, new=1)

    @track_usage("cloud.session.viewer.notebook")
    async def viewer_notebook(self, session_id: str) -> WebsocketService:
        """
        Returns a WebsocketJupyterDisplay for displaying live session replay in Jupyter notebook.
        """
        debug_info = await self.debug_info(session_id=session_id)
        return WebsocketService(
            wss_url=self._with_db_preview(debug_info.ws.recording), process=display_image_in_notebook
        )

    @track_usage("cloud.session.viewer.cdp")
    async def viewer_cdp(self, session_id: str) -> None:
        """
        Opens a browser tab with the debug URL for visualizing the session.

        Retrieves debug information for the specified session and opens
        its debug URL in the default web browser.

        Args:
            session_id (str, optional): The session identifier to use.
                If not provided, the current session ID is used.

        Returns:
            None
        """
        debug_info = await self.debug_info(session_id=session_id)
        _ = await asyncio.to_thread(open_browser, debug_info.debug_url)

    @track_usage("cloud.session.viewer")
    async def viewer(self, session_id: str, _viewer_url: str | None = None) -> None:
        """
        Open the viewer for the session based on the viewer_type.
        """
        match self.viewer_type:
            case SessionViewerType.BROWSER:
                await self.viewer_browser(session_id=session_id, _viewer_url=_viewer_url)
            case SessionViewerType.JUPYTER:
                _ = await self.viewer_notebook(session_id=session_id)
            case SessionViewerType.CDP:
                await self.viewer_cdp(session_id=session_id)


class AsyncRemoteSession:
    """
    The async twin of `RemoteSession`, returned by `AsyncNotteClient.Session`: the same methods, as coroutines.

    **Example:**
    ```python
    from notte_sdk import AsyncNotteClient

    async with AsyncNotteClient() as client:
        async with client.Session() as session:
            _ = await session.execute(type="goto", url="https://www.notte.cc")
            markdown = await session.scrape()
    ```

    Differences from `RemoteSession`:

    - `page` is the async Playwright page (`await session.page`); there is no sync Playwright page,
      so `apage` is not needed.
    - `wait_for_auth` is a coroutine, so `await_for_auth` is not needed.
    - `storage` is an `AsyncRemoteFileStorage`.
    - `client.Session(session_id)` does no I/O: it attaches to the session, and the first method
      that needs its state reads it.
    - There is no sync `with` block: use `async with`.
    """

    @overload
    def __init__(
        self,
        *,
        storage: AsyncRemoteFileStorage | None = None,
        perception_type: PerceptionType = "fast",
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
        perception_type: PerceptionType = "fast",
        cookie_file: str | Path | None = None,
        raise_on_failure: bool = config.raise_on_session_execution_failure,
        open_viewer: bool = False,
        _client: AsyncSessionsClient | None = None,
        **data: Unpack[SessionStartRequestDict],
    ) -> None:
        """
        Create a new AsyncRemoteSession instance with the specified configuration.

        Takes the arguments of `RemoteSession`; `storage` is an `AsyncRemoteFileStorage`, by default
        one on the client's `files`.
        """
        if _client is None:
            raise ValueError("AsyncSessionsClient is required")

        # Filter out open_viewer from data before validating with SessionStartRequest
        # (open_viewer is a RemoteSession parameter, not a SessionStartRequest field)
        request_data = {k: v for k, v in data.items() if k != "open_viewer"}
        self.request: SessionStartRequest = SessionStartRequest.from_data(request_data)
        self._open_viewer: bool = open_viewer

        self.client: AsyncSessionsClient = _client
        self.response: SessionResponse | None = None
        # An attached session's status, read on first use: a constructor cannot await.
        self._attached_id: str | None = session_id
        self.storage: AsyncRemoteFileStorage = storage or AsyncRemoteFileStorage(_client=_client.root_client.files)
        if session_id is not None:
            self.storage = self.storage.for_session(session_id)
        self.default_perception_type: PerceptionType = perception_type
        self.default_raise_on_failure: bool = raise_on_failure
        self._cookie_file: Path | None = Path(cookie_file) if cookie_file is not None else None
        self._async_playwright_context: "PlaywrightAsync | None" = None
        self._async_playwright_browser: "BrowserAsync | None" = None
        self._async_playwright_page: "PageAsync | None" = None

    async def _loaded(self) -> SessionResponse | None:
        """The session's latest response, after reading an attached session's status."""
        if self.response is None and self._attached_id is not None:
            self.response = await self.client.status(session_id=self._attached_id)
            self._attached_id = None
        return self.response

    async def __aenter__(self) -> "AsyncRemoteSession":
        """Start the session and wait for authentication; a cancelled entry stops the session it started."""
        await _guarded_entry(
            self,
            start=lambda: self.start(wait_for_authentication=False),
            wait_for_auth=lambda: self.wait_for_auth(),
            stop=lambda: self.stop(close_reason="error"),
        )
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        """Close the async Playwright connection and stop the session."""

        async def stop(close_reason: Literal["manual", "error"]) -> None:
            await self.stop(close_reason=close_reason)

        await _async_exit(self, exc_val, stop)

    # #######################################################################
    # ############################# Session #################################
    # #######################################################################

    async def start(self, tries: int = 3, *, wait_for_authentication: bool | None = None) -> None:
        """
        Start the session using the configured request.

        We strongly recommend `async with client.Session() as session:` instead, which also stops it.

        Raises:
            ValueError: If the session was already started.
        """
        if await self._loaded() is not None:
            raise ValueError("Session already started")

        self.response = await arun(self.client, _start_flow(self.client, self.request, tries))
        self.storage = self.storage.for_session(self.session_id)

        logger.info(f"[Session] {self.session_id} started")
        should_wait = (
            self.request.wait_for_authentication if wait_for_authentication is None else wait_for_authentication
        )
        if should_wait:
            try:
                await self.wait_for_auth()
            except BaseException:
                await self.stop(close_reason="error")
                raise

        if self._open_viewer:
            await self.viewer()
        # try to load cookies from file
        if self._cookie_file is not None:
            if await asyncio.to_thread(self._cookie_file.exists):
                logger.info(f"🍪 Automatically loading cookies from {self._cookie_file}")
                _ = await self.set_cookies(cookie_file=self._cookie_file)
            else:
                logger.warning(f"🍪 Cookie file {self._cookie_file} not found, skipping cookie loading")

    async def wait_for_auth(self, timeout: float = 615) -> None:
        """Wait for this browser to be ready without restarting or relogging it."""
        response = await self._loaded()
        if response is None:
            raise ValueError("Session has not started")
        if response.status == "active":
            return
        self.response = await arun(self.client, _auth_flow(response.session_id, timeout))

    async def stop(self, close_reason: Literal["manual", "error"] = "manual") -> None:
        """
        Stop the session and clean up resources.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
            RuntimeError: If the session fails to close properly.
        """
        if self._cookie_file is not None:
            try:
                cookies = await self.get_cookies()
                await asyncio.to_thread(create_or_append_cookies_to_file, self._cookie_file, cookies)
            except Exception as e:
                logger.error(f"🍪 Error saving cookies to {self._cookie_file}: {e}")
        try:
            self.response = await self.client.stop(session_id=self.session_id, close_reason=close_reason)
        except Exception as e:
            if _already_stopped(e):
                logger.warning(f"Session {self.session_id} was already stopped")
            else:
                raise

    async def reset(self) -> None:
        """
        Stop the session, then start a new one with the same configuration.

        The new session has a new session ID. A Playwright page must be opened again.
        """
        await self.stop()
        _forget_stopped_session(self)
        self._attached_id = None
        await self.start()

    @property
    def session_id(self) -> str:
        """
        Get the ID of the current session.

        Raises:
            ValueError: If the session hasn't been started yet (no response available).
        """
        if self.response is not None:
            return self.response.session_id
        if self._attached_id is not None:
            return self._attached_id
        raise ValueError("You need to start the session first to get the session id")

    async def offset(self) -> int:
        """Get the trajectory offset of the session."""
        return (await self.client.offset(session_id=self.session_id)).offset

    async def replay(
        self,
        wait: bool = True,
        timeout: float = 240.0,
        poll_interval: float = 5.0,
    ) -> ReplayResponse:
        """
        Get presigned URLs for the session replay; by default, poll until it is ready.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
            TimeoutError: If the replay does not become available within ``timeout`` seconds.
        """
        _ = await self._loaded()
        return await self.client.replay(
            session_id=self.session_id,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
            _session_closed=lambda: self.response is not None and self.response.status == "closed",
        )

    async def viewer_browser(self) -> None:
        """Opens live session replay in browser (frame by frame) in a new browser tab."""
        response = await self._loaded()
        _viewer_url = response.viewer_url if response is not None else None
        return await self.client.viewer_browser(self.session_id, _viewer_url=_viewer_url)

    async def viewer_notebook(self) -> WebsocketService:
        """Returns a WebsocketJupyterDisplay for displaying live session replay in Jupyter notebook."""
        return await self.client.viewer_notebook(session_id=self.session_id)

    async def viewer_cdp(self) -> None:
        """Open a browser tab with the debug URL for visualizing the session."""
        await self.client.viewer_cdp(session_id=self.session_id)

    async def viewer(self) -> None:
        """
        Open the viewer for the session based on the viewer_type.
        """
        match self.client.viewer_type:
            case SessionViewerType.BROWSER:
                await self.viewer_browser()
            case SessionViewerType.JUPYTER:
                _ = await self.viewer_notebook()
            case SessionViewerType.CDP:
                await self.viewer_cdp()

    async def status(self) -> SessionResponse:
        """Get the current status of the session."""
        return await self.client.status(session_id=self.session_id)

    async def set_cookies(
        self,
        cookies: list[CookieDict] | None = None,
        cookie_file: str | Path | None = None,
    ) -> SetCookiesResponse:
        """
        Uploads cookies to the session: `cookies` (list of dicts) or `cookie_file` (json file path).

        Raises:
            ValueError: If both cookies and cookie_file are provided, or if neither is provided.
        """
        return await self.client.set_cookies(session_id=self.session_id, cookies=cookies, cookie_file=cookie_file)

    async def get_cookies(self) -> list[CookieDict]:
        """Gets cookies from the session."""
        return _cookie_dicts(await self.client.get_cookies(session_id=self.session_id))

    async def save_profile(self, profile_id: str | None = None, name: str | None = None) -> ProfileResponse:
        """
        Saves the session's current browser state into a profile, without stopping the session.

        Raises:
            ValueError: If both ``profile_id`` and ``name`` are provided, or if either is empty.
        """
        data = _profile_save_data(profile_id, name)
        return await self.client.save_profile(session_id=self.session_id, **data)

    async def debug_info(self) -> SessionDebugResponse:
        """Get detailed debug information for the session."""
        return await self.client.debug_info(session_id=self.session_id)

    async def cdp_url(self) -> str:
        """
        Get the Chrome DevTools Protocol WebSocket URL for the session.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        if (known := _known_cdp_url(self.client, self.request, await self._loaded())) is not None:
            return known
        # cdp url from the session provider
        return self.client._with_db_preview((await self.debug_info()).ws.cdp)  # pyright: ignore [reportPrivateUsage]

    def _cdp_headers(self, cdp_url: str) -> dict[str, str] | None:
        """Headers for this API's CDP connection: the SDK identity, and the runner capability if set."""
        return _cdp_headers(self.client, self.request, cdp_url)

    @property
    async def page(self) -> "PageAsync":
        """
        Get an async Playwright page connected to the session via CDP.

        The connection is established lazily on first access and cached for subsequent calls.

        ```python
        page = await session.page
        await page.goto("https://www.google.com")
        ```

        Raises:
            ImportError: If playwright is not installed. Install with `pip install notte-sdk[playwright]`
        """
        return await _async_page(self, self.cdp_url)

    # #######################################################################
    # ############################# PAGE ####################################
    # #######################################################################

    # response_format provided, raise_on_failure=True (default) -> unwrapped TBaseModel
    @overload
    async def scrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> TBaseModel: ...

    # response_format provided, raise_on_failure=False -> wrapped StructuredData[TBaseModel]
    @overload
    async def scrape(
        self,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    # instructions only, raise_on_failure=True (default) -> unwrapped BaseModel as dict
    @overload
    async def scrape(
        self, *, instructions: str, raise_on_failure: Literal[True] = ..., **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> dict[str, Any]: ...

    # instructions only, raise_on_failure=False -> wrapped StructuredData[BaseModel]
    @overload
    async def scrape(
        self, *, instructions: str, raise_on_failure: Literal[False], **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> StructuredData[BaseModel]: ...

    # markdown catch-all LAST: open Unpack[TypedDict] otherwise swallows every kwargs call under ty
    @overload
    async def scrape(self, /, *, raise_on_failure: bool = True, **params: Unpack[ScrapeMarkdownParamsDict]) -> str: ...

    async def scrape(
        self, *, raise_on_failure: bool = True, **data: Unpack[ScrapeRequestDict]
    ) -> StructuredData[BaseModel] | BaseModel | dict[str, Any] | str:
        """
        Scrape the current page data: markdown, or structured data with `response_format` or `instructions`.

        Returns:
            Extracted data as structured data, markdown text, or a StructuredData wrapper when
            ``raise_on_failure=False``.
        """
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
        """
        Observes the current session page: its actions, a screenshot and metadata.

        Deprecated: `perception_type='deep'` and `instructions` are removed on December 1, 2026, and passing
        either emits a `DeprecationWarning`. See the migration guide: https://docs.notte.cc/features/sessions/observe-migration
        """
        data = _with_perception(data, self.default_perception_type)
        return await self.client.page.observe(session_id=self.session_id, **data)  # pyright: ignore[reportUnknownVariableType, reportArgumentType, reportCallIssue]

    # BEGIN GENERATED OVERLOADS: AsyncRemoteSession.execute (scripts/generate_action_overloads.py)
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
        self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[EmailVerificationReadActionDict]
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

    # END GENERATED OVERLOADS: AsyncRemoteSession.execute

    async def execute(
        self,
        action: BaseAction | None = None,
        *,
        raise_on_failure: bool | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Executes an action on the current session page, given as an action object or as keyword arguments.

        Raises:
            Exception: If raise_on_failure is True and the action execution fails.
        """
        action_obj = _action_from(action, kwargs)
        result = await self.client.page.execute(session_id=self.session_id, action=action_obj)
        return _checked_execution(result, action_obj, raise_on_failure, self.default_raise_on_failure)

    # raise_on_failure=True (default) -> the evaluated string; failures raise
    @overload
    async def evaluate_js(self, code: str, *, raise_on_failure: Literal[True] = ...) -> str: ...

    # raise_on_failure=False -> the ExecutionResult envelope, like execute()
    @overload
    async def evaluate_js(self, code: str, *, raise_on_failure: Literal[False]) -> ExecutionResult: ...

    async def evaluate_js(self, code: str, *, raise_on_failure: bool = True) -> str | ExecutionResult:
        """Evaluate JavaScript on the current page and return its result as a string."""
        return _evaluated(
            await self.execute(type="evaluate_js", code=code, raise_on_failure=raise_on_failure), raise_on_failure
        )

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: FetchData | None = None,
        timeout: float | None = None,
    ) -> FetchResponse:
        """Issue an HTTP request from the page the session is on and return the response."""
        script = build_fetch_script(
            url, method=method, headers=headers, params=params, json_body=json, data=data, timeout=timeout
        )
        return response_from_evaluated(await self.evaluate_js(script))
