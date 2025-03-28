from collections.abc import Sequence
from typing import Unpack
from webbrowser import open as open_browser

from pydantic import BaseModel
from typing_extensions import final, override

from notte.errors.sdk import InvalidRequestError
from notte.sdk.endpoints.base import BaseClient, NotteEndpoint
from notte.sdk.types import (
    ListRequestDict,
    SessionDebugResponse,
    SessionListRequest,
    SessionRequest,
    SessionResponse,
    SessionStartRequestDict,
    TabSessionDebugRequest,
    TabSessionDebugResponse,
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

    def __init__(
        self,
        api_key: str | None = None,
    ):
        """
        Initialize a SessionsClient instance.

        Initializes the client with an optional API key and server URL for session management,
        setting the base endpoint to "sessions". Also initializes the last session response to None.
        """
        super().__init__(base_endpoint_path="sessions", api_key=api_key)
        self._last_session_response: SessionResponse | None = None

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
        ]

    @property
    def session_id(self) -> str | None:
        """
        Return the session ID from the last session response, or None if no session exists.

        Returns:
            str or None: The active session ID, or None when no session has been started.
        """
        return self._last_session_response.session_id if self._last_session_response is not None else None

    def get_session_id(self, session_id: str | None = None) -> str:
        """
        Retrieves the session ID for session operations.

        If a session ID is provided as an argument, it is returned directly. Otherwise,
        the session ID is extracted from the last session response. Raises a ValueError
        if neither a provided session ID nor a prior session response is available.

        Args:
            session_id: Optional; an explicit session ID to use.

        Returns:
            The session ID as a string.

        Raises:
            ValueError: If no session ID is available.
        """
        if session_id is None:
            if self._last_session_response is None:
                raise InvalidRequestError("No session to get session id from")
            session_id = self._last_session_response.session_id
        return session_id

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
        request = SessionRequest.model_validate(data)
        response = self.request(SessionsClient.session_start_endpoint().with_request(request))
        self._last_session_response = response
        return response

    def close(self, session_id: str | None = None) -> SessionResponse:
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
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_close_endpoint(session_id=session_id)
        response = self.request(endpoint)
        self._last_session_response = None
        return response

    def status(self, session_id: str | None = None) -> SessionResponse:
        """
        Retrieves the current status of a session.

        If no session_id is provided, the session ID from the last response is used. This method constructs
        the status endpoint, validates the response against the SessionResponse model, updates the stored
        session response, and returns the validated status.
        """
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_status_endpoint(session_id=session_id)
        response = self.request(endpoint)
        self._last_session_response = response
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

    def debug_info(self, session_id: str | None = None) -> SessionDebugResponse:
        """
        Retrieves debug information for a session.

        If a session ID is provided, it is used; otherwise, the current session ID is retrieved.
        Raises a ValueError if no valid session ID is available.

        Args:
            session_id (Optional[str]): An optional session identifier to use.

        Returns:
            SessionDebugResponse: The debug information response for the session.
        """
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_debug_endpoint(session_id=session_id)
        return self.request(endpoint)

    def debug_tab_info(self, session_id: str | None = None, tab_idx: int | None = None) -> TabSessionDebugResponse:
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
        session_id = self.get_session_id(session_id)
        params = TabSessionDebugRequest(tab_idx=tab_idx) if tab_idx is not None else None
        endpoint = SessionsClient.session_debug_tab_endpoint(session_id=session_id, params=params)
        return self.request(endpoint)

    def viewer(self, session_id: str | None = None) -> None:
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
