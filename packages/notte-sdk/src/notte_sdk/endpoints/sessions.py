from collections.abc import Sequence
from pathlib import Path
from typing import Any, Unpack
from webbrowser import open as open_browser

from loguru import logger
from notte_core.common.resource import SyncResource
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import (
    ListRequestDict,
    SessionDebugResponse,
    SessionListRequest,
    SessionResponse,
    SessionStartRequest,
    SessionStartRequestDict,
    TabSessionDebugRequest,
    TabSessionDebugResponse,
    UploadCookiesRequest,
    UploadCookiesResponse,
)


@final
class SessionsClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    SESSION_START = "start"
    SESSION_CLOSE = "{session_id}/close"
    SESSION_STATUS = "{session_id}"
    SESSION_LIST = ""
    SESSION_DEBUG = "debug/{session_id}"
    SESSION_DEBUG_TAB = "debug/{session_id}/tab"
    SESSION_DEBUG_REPLAY = "debug/{session_id}/replay"
    # upload files
    SESSION_UPLOAD_FILES_COOKIES = "files/cookies"

    def __init__(
        self,
        api_key: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize a SessionsClient instance.

        Initializes the client with an optional API key and server URL for session management,
        setting the base endpoint to "sessions". Also initializes the last session response to None.
        """
        super().__init__(base_endpoint_path="sessions", api_key=api_key, verbose=verbose)

    @staticmethod
    def session_start_endpoint() -> NotteEndpoint[SessionResponse]:
        """
        Returns a NotteEndpoint configured for starting a session.

        The returned endpoint uses the session start path from SessionsClient with the POST method and expects a SessionResponse.
        """
        return NotteEndpoint(path=SessionsClient.SESSION_START, response=SessionResponse, method="POST")

    @staticmethod
    def session_close_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Constructs a DELETE endpoint for closing a session.

        If a session ID is provided, it is inserted into the endpoint path. Returns a NotteEndpoint configured
        with the DELETE method and expecting a SessionResponse.

        Args:
            session_id: Optional session identifier; if provided, it is formatted into the endpoint path.

        Returns:
            A NotteEndpoint instance for closing a session.
        """
        path = SessionsClient.SESSION_CLOSE
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
    def session_upload_cookies_endpoint() -> NotteEndpoint[UploadCookiesResponse]:
        """
        Returns a NotteEndpoint for uploading cookies to a session.
        """
        return NotteEndpoint(
            path=SessionsClient.SESSION_UPLOAD_FILES_COOKIES, response=UploadCookiesResponse, method="POST"
        )

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns a sequence of available session endpoints.

        Aggregates endpoints from SessionsClient for starting, closing, status checking, listing,
        and debugging sessions (including tab-specific debugging)."""
        return [
            SessionsClient.session_start_endpoint(),
            SessionsClient.session_close_endpoint(),
            SessionsClient.session_status_endpoint(),
            SessionsClient.session_list_endpoint(),
            SessionsClient.session_debug_endpoint(),
            SessionsClient.session_debug_tab_endpoint(),
            SessionsClient.session_debug_replay_endpoint(),
            SessionsClient.session_upload_cookies_endpoint(),
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

    def close(self, session_id: str) -> SessionResponse:
        """
        Closes an active session.

        This method sends a request to the session close endpoint using the specified
        session ID or the currently active session. It validates the server response,
        clears the internal session state, and returns the validated response.

        Parameters:
            session_id (str, optional): The identifier of the session to close. If not
                provided, the active session ID is used. Raises ValueError if no active
                session exists.

        Returns:
            SessionResponse: The validated response from the session close request.
        """
        endpoint = SessionsClient.session_close_endpoint(session_id=session_id)
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

    def list(self, **data: Unpack[ListRequestDict]) -> Sequence[SessionResponse]:
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

    def replay(self, session_id: str, output_file: str | None = None) -> bytes:
        """
        Downloads the replay for the specified session in webp format.

        Args:
            session_id: The identifier of the session to download the replay for.
            output_file: The path to save the replay file.

        Returns:
            bytes: The replay file in webp format.
        """
        endpoint = SessionsClient.session_debug_replay_endpoint(session_id=session_id)
        return self._request_file(endpoint, file_type="webp", output_file=output_file)

    def upload_cookies(self, cookie_file: str | Path) -> UploadCookiesResponse:
        """
        Uploads cookies to the session.

        Args:
            cookie_file: The path to the cookie file (json format)
        """
        request = UploadCookiesRequest.from_json(cookie_file)
        endpoint = SessionsClient.session_upload_cookies_endpoint()
        return self.request(endpoint.with_request(request))

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


@final
class RemoteSessionFactory:
    class RemoteSession(SyncResource):
        def __init__(self, client: SessionsClient, request: SessionStartRequest) -> None:
            self.request: SessionStartRequest = request
            self.client: SessionsClient = client
            self.response: SessionResponse | None = None

        @override
        def start(self) -> None:
            self.response = self.client.start(**self.request.model_dump())
            logger.info(
                f"[Session] {self.session_id} started with request: {self.request.model_dump(exclude_none=True)}"
            )

        @override
        def stop(self) -> None:
            logger.info(f"[Session] {self.session_id} closed")
            self.response = self.client.close(session_id=self.session_id)
            if self.response.status != "closed":
                raise RuntimeError(f"[Session] {self.session_id} failed to close")

        @property
        def session_id(self) -> str:
            """
            Return the session ID from the last session response, or None if no session exists.

            Returns:
                str or None: The active session ID, or None when no session has been started.
            """
            if self.response is None:
                raise ValueError("You need to start the session first to get the session id")
            return self.response.session_id

        def replay(self, output_file: str | None = None) -> bytes:
            if self.response is None:
                raise ValueError("You need to start the session first to replay it")
            return self.client.replay(session_id=self.response.session_id, output_file=output_file)

        def display_replay(self) -> Any:
            from IPython.display import Image

            replay = self.replay()
            return Image(replay, format="webp")

        def viewer(self) -> None:
            self.client.viewer(session_id=self.session_id)

        def status(self) -> SessionResponse:
            return self.client.status(session_id=self.session_id)

        def debug_info(self) -> SessionDebugResponse:
            return self.client.debug_info(session_id=self.session_id)

        def cdp_url(self) -> str:
            debug = self.debug_info()
            return debug.ws_url

    def __init__(self, client: SessionsClient) -> None:
        self.client = client

    def __call__(self, **data: Unpack[SessionStartRequestDict]) -> RemoteSession:
        request = SessionStartRequest.model_validate(data)
        return RemoteSessionFactory.RemoteSession(self.client, request)
