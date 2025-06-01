from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import List, Unpack  # pyright: ignore [reportDeprecated]
from urllib.parse import urljoin
from webbrowser import open as open_browser

from loguru import logger
from notte_core.common.resource import SyncResource
from notte_core.utils.webp_replay import WebpReplay
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.page import PageClient
from notte_sdk.types import (
    Cookie,
    GetCookiesResponse,
    ObserveRequestDict,
    ObserveResponse,
    ScrapeRequestDict,
    ScrapeResponse,
    SessionDebugResponse,
    SessionListRequest,
    SessionListRequestDict,
    SessionResponse,
    SessionStartRequest,
    SessionStartRequestDict,
    SetCookiesRequest,
    SetCookiesResponse,
    StepRequestDict,
    StepResponse,
    TabSessionDebugRequest,
    TabSessionDebugResponse,
)
from notte_sdk.websockets.base import WebsocketService
from notte_sdk.websockets.jupyter import display_image_in_notebook


class SessionViewerType(StrEnum):
    CDP = "cdp"
    BROWSER = "browser"
    JUPYTER = "jupyter"


@final
class SessionsClient(BaseClient):
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

    def __init__(
        self,
        api_key: str | None = None,
        verbose: bool = False,
        viewer_type: SessionViewerType = SessionViewerType.BROWSER,
    ):
        """
        Initialize a SessionsClient instance.

        Initializes the client with an optional API key and server URL for session management,
        setting the base endpoint to "sessions". Also initializes the last session response to None.
        """
        super().__init__(base_endpoint_path="sessions", api_key=api_key, verbose=verbose)
        self.page: PageClient = PageClient(api_key=api_key, verbose=verbose)
        self.viewer_type: SessionViewerType = viewer_type

    @staticmethod
    def session_start_endpoint() -> NotteEndpoint[SessionResponse]:
        """
        Returns a NotteEndpoint configured for starting a session.

        The returned endpoint uses the session start path from SessionsClient with the POST method and expects a SessionResponse.
        """
        return NotteEndpoint(path=SessionsClient.SESSION_START, response=SessionResponse, method="POST")

    @staticmethod
    def session_stop_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Constructs a DELETE endpoint for closing a session.

        If a session ID is provided, it is inserted into the endpoint path. Returns a NotteEndpoint configured
        with the DELETE method and expecting a SessionResponse.

        Args:
            session_id: Optional session identifier; if provided, it is formatted into the endpoint path.

        Returns:
            A NotteEndpoint instance for closing a session.
        """
        path = SessionsClient.SESSION_STOP
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="DELETE")

    @staticmethod
    def session_status_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Returns a NotteEndpoint for retrieving the status of a session.

        If a session_id is provided, it is interpolated into the endpoint path.
        The endpoint uses the GET method and expects a SessionResponse.
        """
        path = SessionsClient.SESSION_STATUS
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="GET")

    @staticmethod
    def session_list_endpoint(params: SessionListRequest | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Constructs a NotteEndpoint for listing sessions.

        Args:
            params (SessionListRequest, optional): Additional filter parameters for the session list request.

        Returns:
            NotteEndpoint[SessionResponse]: An endpoint configured with the session list path and a GET method.
        """
        return NotteEndpoint(
            path=SessionsClient.SESSION_LIST,
            response=SessionResponse,
            method="GET",
            request=None,
            params=params,
        )

    @staticmethod
    def session_debug_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionDebugResponse]:
        """
        Creates a NotteEndpoint for retrieving session debug information.

        If a session ID is provided, it is interpolated into the endpoint path.
        The returned endpoint uses the GET method and expects a SessionDebugResponse.
        """
        path = SessionsClient.SESSION_DEBUG
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionDebugResponse, method="GET")

    @staticmethod
    def session_debug_tab_endpoint(
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

    @staticmethod
    def session_debug_replay_endpoint(session_id: str | None = None) -> NotteEndpoint[BaseModel]:
        """
        Returns an endpoint for retrieving the replay for a session.
        """
        path = SessionsClient.SESSION_DEBUG_REPLAY
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=BaseModel, method="GET")

    @staticmethod
    def session_set_cookies_endpoint(session_id: str | None = None) -> NotteEndpoint[SetCookiesResponse]:
        """
        Returns a NotteEndpoint for uploading cookies to a session.
        """
        path = SessionsClient.SESSION_SET_COOKIES
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SetCookiesResponse, method="POST")

    @staticmethod
    def session_get_cookies_endpoint(session_id: str | None = None) -> NotteEndpoint[GetCookiesResponse]:
        """
        Returns a NotteEndpoint for retrieving cookies from a session.
        """
        path = SessionsClient.SESSION_GET_COOKIES
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=GetCookiesResponse, method="GET")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns a sequence of available session endpoints.

        Aggregates endpoints from SessionsClient for starting, closing, status checking, listing,
        and debugging sessions (including tab-specific debugging)."""
        return [
            SessionsClient.session_start_endpoint(),
            SessionsClient.session_stop_endpoint(),
            SessionsClient.session_status_endpoint(),
            SessionsClient.session_list_endpoint(),
            SessionsClient.session_debug_endpoint(),
            SessionsClient.session_debug_tab_endpoint(),
            SessionsClient.session_debug_replay_endpoint(),
            SessionsClient.session_set_cookies_endpoint(),
            SessionsClient.session_get_cookies_endpoint(),
        ]

    def start(self, **data: Unpack[SessionStartRequestDict]) -> SessionResponse:
        """
        Starts a new session using the provided keyword arguments.

        Validates the input data against the session start model, sends a session start
        request to the API, updates the last session response, and returns the response.

        Args:
            **data: Keyword arguments representing details for starting the session.

        Returns:
            SessionResponse: The response received from the session start endpoint.
        """
        request = SessionStartRequest.model_validate(data)
        response = self.request(SessionsClient.session_start_endpoint().with_request(request))
        return response

    def stop(self, session_id: str) -> SessionResponse:
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
        endpoint = SessionsClient.session_stop_endpoint(session_id=session_id)
        response = self.request(endpoint)
        return response

    def status(self, session_id: str) -> SessionResponse:
        """
        Retrieves the current status of a session.

        If no session_id is provided, the session ID from the last response is used. This method constructs
        the status endpoint, validates the response against the SessionResponse model, updates the stored
        session response, and returns the validated status.
        """
        endpoint = SessionsClient.session_status_endpoint(session_id=session_id)
        response = self.request(endpoint)
        return response

    def list(self, **data: Unpack[SessionListRequestDict]) -> Sequence[SessionResponse]:
        """
        Retrieves a list of sessions from the API.

        Validates keyword arguments as session listing criteria and requests the available
        sessions. Returns a sequence of session response objects.
        """
        params = SessionListRequest.model_validate(data)
        endpoint = SessionsClient.session_list_endpoint(params=params)
        return self.request_list(endpoint)

    def debug_info(self, session_id: str) -> SessionDebugResponse:
        """
        Retrieves debug information for a session.

        If a session ID is provided, it is used; otherwise, the current session ID is retrieved.
        Raises a ValueError if no valid session ID is available.

        Args:
            session_id (Optional[str]): An optional session identifier to use.

        Returns:
            SessionDebugResponse: The debug information response for the session.
        """
        endpoint = SessionsClient.session_debug_endpoint(session_id=session_id)
        return self.request(endpoint)

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
        params = TabSessionDebugRequest(tab_idx=tab_idx) if tab_idx is not None else None
        endpoint = SessionsClient.session_debug_tab_endpoint(session_id=session_id, params=params)
        return self.request(endpoint)

    def replay(self, session_id: str) -> WebpReplay:
        """
        Downloads the replay for the specified session in webp format.

        Args:
            session_id: The identifier of the session to download the replay for.

        Returns:
            WebpReplay: The replay file in webp format.
        """
        endpoint = SessionsClient.session_debug_replay_endpoint(session_id=session_id)
        file_bytes = self._request_file(endpoint, file_type="webp")
        return WebpReplay(file_bytes)

    def display_in_browser(self, session_id: str) -> None:
        """
        Opens live session replay in browser (frame by frame)
        """
        debug_info = self.debug_info(session_id=session_id)

        base_url = urljoin(self.server_url + "/", f"{self.base_endpoint_path}/{self.SESSION_VIEWER}/")
        viewer_url = urljoin(base_url, f"index.html?ws={debug_info.ws.recording}")
        _ = open_browser(viewer_url, new=1)

    def display_in_notebook(self, session_id: str) -> WebsocketService:
        """
        Returns a WebsocketJupyterDisplay for displaying live session replay in Jupyter notebook.
        """
        debug_info = self.debug_info(session_id=session_id)
        return WebsocketService(wss_url=debug_info.ws.recording, process=display_image_in_notebook)

    def set_cookies(
        self,
        session_id: str,
        cookies: List[Cookie] | None = None,  # pyright: ignore [reportDeprecated]
        cookie_file: str | Path | None = None,
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
        endpoint = SessionsClient.session_set_cookies_endpoint(session_id=session_id)

        if cookies is not None and cookie_file is not None:
            raise ValueError("Cannot provide both cookies and cookie_file")

        if cookies is not None:
            request = SetCookiesRequest(cookies=cookies)
        elif cookie_file is not None:
            request = SetCookiesRequest.from_json(cookie_file)
        else:
            raise ValueError("Have to provide either cookies or cookie_file")

        return self.request(endpoint.with_request(request))

    def get_cookies(self, session_id: str) -> GetCookiesResponse:
        """
        Gets cookies from the session.

        Returns:
            GetCookiesResponse: the response containing the list of cookies in the session
        """
        endpoint = SessionsClient.session_get_cookies_endpoint(session_id=session_id)
        return self.request(endpoint)

    def viewer(self, session_id: str) -> None:
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

    def __init__(self, client: SessionsClient, request: SessionStartRequest) -> None:
        """
        Initialize a new RemoteSession instance.

        Args:
            client (SessionsClient): The client used to communicate with the Notte API.
            request (SessionStartRequest): The configuration request for this session.
        """
        self.request: SessionStartRequest = request
        self._open_viewer: bool = not self.request.headless
        # always run in headless mode on the API
        self.request.headless = True
        self.client: SessionsClient = client
        self.response: SessionResponse | None = None

    # #######################################################################
    # ############################# Session #################################
    # #######################################################################

    @override
    def start(self) -> None:
        """
        Start the session using the configured request.

        This method sends a start request to the API and logs the session ID
        and request details upon successful start.

        Raises:
            ValueError: If the session request is invalid.
        """
        self.response = self.client.start(**self.request.model_dump())
        logger.info(f"[Session] {self.session_id} started with request: {self.request.model_dump(exclude_none=True)}")
        if self._open_viewer:
            match self.client.viewer_type:
                case SessionViewerType.BROWSER:
                    self.display_in_browser()
                case SessionViewerType.JUPYTER:
                    _ = self.display_in_notebook()
                case SessionViewerType.CDP:
                    self.viewer()

    @override
    def stop(self) -> None:
        """
        Stop the session and clean up resources.

        This method sends a close request to the API and verifies that the session
        was properly closed. It logs the session closure and raises an error if
        the session fails to close.

        Raises:
            ValueError: If the session hasn't been started (no session_id available).
            RuntimeError: If the session fails to close properly.
        """
        logger.info(f"[Session] {self.session_id} stopped")
        self.response = self.client.stop(session_id=self.session_id)
        if self.response.status != "closed":
            raise RuntimeError(f"[Session] {self.session_id} failed to stop")

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

    def replay(self) -> WebpReplay:
        """
        Get a replay of the session's execution in WEBP format.

        Returns:
            WebpReplay: The replay data in WEBP format.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        return self.client.replay(session_id=self.session_id)

    def display_in_browser(self) -> None:
        """
        Opens live session replay in browser (frame by frame)
        """
        return self.client.display_in_browser(self.session_id)

    def display_in_notebook(self) -> WebsocketService:
        """
        Returns a WebsocketJupyterDisplay for displaying live session replay in Jupyter notebook.
        """
        return self.client.display_in_notebook(session_id=self.session_id)

    def viewer(self) -> None:
        """
        Open a browser tab with the debug URL for visualizing the session.

        This method opens the default web browser to display the session's debug interface.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        self.client.viewer(session_id=self.session_id)

    def status(self) -> SessionResponse:
        """
        Get the current status of the session.

        Returns:
            SessionResponse: The current status information of the session.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        return self.client.status(session_id=self.session_id)

    def set_cookies(
        self,
        cookies: List[Cookie] | None = None,  # pyright: ignore [reportDeprecated]
        cookie_file: str | Path | None = None,
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
        return self.client.set_cookies(session_id=self.session_id, cookies=cookies, cookie_file=cookie_file)

    def get_cookies(self) -> GetCookiesResponse:
        """
        Gets cookies from the session.

        Returns:
            GetCookiesResponse: the response containing the list of cookies in the session
        """
        return self.client.get_cookies(session_id=self.session_id)

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

        This URL can be used to connect to the browser's debugging interface.

        Returns:
            str: The WebSocket URL for the Chrome DevTools Protocol.

        Raises:
            ValueError: If the session hasn't been started yet (no session_id available).
        """
        debug = self.debug_info()
        return debug.ws.cdp

    # #######################################################################
    # ############################# PAGE ####################################
    # #######################################################################

    def scrape(self, **data: Unpack[ScrapeRequestDict]) -> ScrapeResponse:
        return self.client.page.scrape(session_id=self.session_id, **data)

    def observe(self, **data: Unpack[ObserveRequestDict]) -> ObserveResponse:
        return self.client.page.observe(session_id=self.session_id, **data)

    def step(self, **data: Unpack[StepRequestDict]) -> StepResponse:
        return self.client.page.step(session_id=self.session_id, **data)


@final
class RemoteSessionFactory:
    """
    Factory for creating RemoteSession instances.

    This factory provides a convenient way to create RemoteSession instances with
    customizable configurations. It handles the validation of session creation requests
    and sets up the appropriate connections.

    Attributes:
        client (SessionsClient): The client used to communicate with the Notte API.
    """

    def __init__(self, client: SessionsClient) -> None:
        """
        Initialize a new RemoteSessionFactory instance.

        Args:
            client (SessionsClient): The client used to communicate with the Notte API.
        """
        self.client = client

    def __call__(self, **data: Unpack[SessionStartRequestDict]) -> RemoteSession:
        """
        Create a new RemoteSession instance with the specified configuration.

        This method validates the session creation request and returns a new
        RemoteSession instance configured with the specified parameters.

        Args:
            **data: Keyword arguments for the session creation request.

        Returns:
            RemoteSession: A new RemoteSession instance configured with the specified parameters.
        """
        request = SessionStartRequest.model_validate(data)
        return RemoteSession(self.client, request)
