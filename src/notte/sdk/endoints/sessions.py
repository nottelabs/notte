from collections.abc import Sequence
from typing import Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte.sdk.endoints.base import BaseClient, NotteEndpoint
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
        server_url: str | None = None,
    ):
        """
        Initialize a SessionsClient instance.
        
        Creates a new client for handling session operations via the Notte API. An optional API key and server URL may be provided for authentication and service routing. The client begins with no prior session response.
        """
        super().__init__(base_endpoint_path="sessions", api_key=api_key, server_url=server_url)
        self._last_session_response: SessionResponse | None = None

    @staticmethod
    def session_start_endpoint() -> NotteEndpoint[SessionResponse]:
        """
        Returns a NotteEndpoint for starting a session.
        
        This function constructs and returns a NotteEndpoint configured with the session 
        start path (SessionsClient.SESSION_START), the POST HTTP method, and SessionResponse 
        as the expected response type.
        """
        return NotteEndpoint(path=SessionsClient.SESSION_START, response=SessionResponse, method="POST")

    @staticmethod
    def session_close_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Generates a DELETE endpoint to close a session.
        
        If a session ID is provided, it is formatted into the endpoint path; otherwise, the base path is used.
        Returns a NotteEndpoint configured to handle the session close response.
        """
        path = SessionsClient.SESSION_CLOSE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="DELETE")

    @staticmethod
    def session_status_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Constructs an endpoint to retrieve a session's status.
        
        If a session ID is provided, it is substituted into the endpoint path; otherwise,
        the base status endpoint is used. Returns a GET endpoint configured to receive a
        SessionResponse.
        
        Parameters:
            session_id (Optional[str]): The session identifier for formatting into the path.
        
        Returns:
            NotteEndpoint[SessionResponse]: The endpoint for querying session status.
        """
        path = SessionsClient.SESSION_STATUS
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="GET")

    @staticmethod
    def session_list_endpoint(params: SessionListRequest | None = None) -> NotteEndpoint[SessionResponse]:
        """
        Constructs a NotteEndpoint for listing sessions.
        
        If provided, 'params' specifies additional query parameters for filtering the session list.
        Returns a NotteEndpoint configured to perform a GET request to retrieve session data.
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
        Returns an endpoint for retrieving debug information for a session.
        
        If a session identifier is provided, it is inserted into the endpoint path. The returned
        NotteEndpoint is configured for a GET request and expects a response of type SessionDebugResponse.
        
        Args:
            session_id: Optional session identifier to include in the endpoint path.
        
        Returns:
            A NotteEndpoint configured for a debug GET request.
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
        Constructs a NotteEndpoint for retrieving debug information for a specific session tab.
        
        If a session_id is provided, the endpoint path is formatted with this ID. Optional
        parameters for debugging can also be supplied.
        
        Returns:
            A NotteEndpoint configured with the tab debug endpoint path, GET method, and the
            expected response type TabSessionDebugResponse.
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
        """
        Returns a sequence of endpoints for managing session operations.
        
        The returned list includes endpoints for starting, closing, checking status,
        listing sessions, and retrieving debug information for sessions and specific tabs.
        """
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
        Retrieves the session ID from the last session response.
        
        Returns:
            The session identifier if a session response exists, otherwise None.
        """
        return self._last_session_response.session_id if self._last_session_response is not None else None

    def get_session_id(self, session_id: str | None = None) -> str:
        """
        Retrieves the session ID from the provided argument or stored session response.
        
        If a session ID is supplied, it is returned immediately. Otherwise, the method
        extracts the session ID from the last session response. A ValueError is raised if
        no session information is available.
            
        Args:
            session_id: Optional; an externally provided session ID. If None, the session ID
                        from the last session response is used.
                        
        Returns:
            The session ID as a string.
            
        Raises:
            ValueError: If no session ID is provided and no session response exists.
        """
        if session_id is None:
            if self._last_session_response is None:
                raise ValueError("No session to get session id from")
            session_id = self._last_session_response.session_id
        return session_id

    def start(self, **data: Unpack[SessionStartRequestDict]) -> SessionResponse:
        """
        Starts a new session using provided session parameters.
        
        Validates the input data against the session request model, sends a request to the
        session start endpoint, and updates the client's last session response with the
        received session details.
        
        Keyword Args:
            **data: Arbitrary keyword arguments representing the session start parameters.
        
        Returns:
            SessionResponse: The response object containing details of the initiated session.
        """
        request = SessionRequest.model_validate(data)
        response = self.request(SessionsClient.session_start_endpoint().with_request(request))
        self._last_session_response = response
        return response

    def close(self, session_id: str | None = None) -> SessionResponse:
        """
        Close the active session.
        
        If a session ID is provided, it is used; otherwise, the current session ID from the last session
        response is retrieved. The method sends a request to the session close endpoint, clears the stored
        session response, and returns the validated response.
        
        Args:
            session_id: Optional session identifier to close. If None, the active session is used.
        
        Returns:
            SessionResponse: The response from the session close operation.
        
        Raises:
            ValueError: If no valid session identifier is available.
        """
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_close_endpoint(session_id=session_id)
        response = SessionResponse.model_validate(self.request(endpoint))
        self._last_session_response = None
        return response

    def status(self, session_id: str | None = None) -> SessionResponse:
        """Retrieve the status of a session.
        
        Retrieves and validates the status of a session from the API. If a session ID is provided, that ID is used;
        otherwise, the client's stored session ID is used, and a ValueError is raised if no such ID exists.
        The response is validated against the SessionResponse model and saved as the last session response.
        
        Parameters:
            session_id: Optional; the identifier of the session whose status is to be retrieved.
        
        Returns:
            SessionResponse: The validated status response for the session.
        """
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_status_endpoint(session_id=session_id)
        response = SessionResponse.model_validate(self.request(endpoint))
        self._last_session_response = response
        return response

    def list(self, **data: Unpack[ListRequestDict]) -> Sequence[SessionResponse]:
        """
        Lists sessions using optional filter criteria.
        
        Validates the provided keyword arguments against the SessionListRequest
        model, constructs the corresponding API endpoint, and returns a sequence of
        session responses.
            
        Args:
            **data: Optional filter parameters to narrow down the session list.
            
        Returns:
            A sequence of SessionResponse objects.
        """
        params = SessionListRequest.model_validate(data)
        endpoint = SessionsClient.session_list_endpoint(params=params)
        return self.request_list(endpoint)

    def debug_info(self, session_id: str | None = None) -> SessionDebugResponse:
        """
        Retrieves debug information for a session.
        
        If no session_id is provided, the current session identifier is obtained from the last session response.
        Raises ValueError if a valid session identifier is not available.
        
        Args:
            session_id: Optional session identifier for which to retrieve debug information.
        
        Returns:
            SessionDebugResponse: The debug information associated with the session.
        """
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_debug_endpoint(session_id=session_id)
        return self.request(endpoint)

    def debug_tab_info(self, session_id: str | None = None, tab_idx: int | None = None) -> TabSessionDebugResponse:
        """
        Retrieves debug information for a specific session tab.
        
        If no session ID is provided, the current session ID is used. Optionally, a tab index may be specified to obtain
        debug information for a particular tab. Raises ValueError if no valid session exists.
        
        Args:
            session_id: Optional identifier of the session. If not provided, the last session's ID is used.
            tab_idx: Optional index of the tab for which to retrieve debug information.
        
        Returns:
            TabSessionDebugResponse: The debug information for the specified session tab.
        """
        session_id = self.get_session_id(session_id)
        params = TabSessionDebugRequest(tab_idx=tab_idx) if tab_idx is not None else None
        endpoint = SessionsClient.session_debug_tab_endpoint(session_id=session_id, params=params)
        return self.request(endpoint)
