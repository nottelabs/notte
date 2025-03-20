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
        super().__init__(base_endpoint_path="sessions", api_key=api_key, server_url=server_url)
        self._last_session_response: SessionResponse | None = None

    @staticmethod
    def session_start_endpoint() -> NotteEndpoint[SessionResponse]:
        return NotteEndpoint(path=SessionsClient.SESSION_START, response=SessionResponse, method="POST")

    @staticmethod
    def session_close_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        path = SessionsClient.SESSION_CLOSE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="DELETE")

    @staticmethod
    def session_status_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionResponse]:
        path = SessionsClient.SESSION_STATUS
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionResponse, method="GET")

    @staticmethod
    def session_list_endpoint(params: SessionListRequest | None = None) -> NotteEndpoint[SessionResponse]:
        return NotteEndpoint(
            path=SessionsClient.SESSION_LIST,
            response=SessionResponse,
            method="GET",
            request=None,
            params=params,
        )

    @staticmethod
    def session_debug_endpoint(session_id: str | None = None) -> NotteEndpoint[SessionDebugResponse]:
        path = SessionsClient.SESSION_DEBUG
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=SessionDebugResponse, method="GET")

    @staticmethod
    def session_debug_tab_endpoint(
        session_id: str | None = None, params: TabSessionDebugRequest | None = None
    ) -> NotteEndpoint[TabSessionDebugResponse]:
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
        return self._last_session_response.session_id if self._last_session_response is not None else None

    def get_session_id(self, session_id: str | None = None) -> str:
        if session_id is None:
            if self._last_session_response is None:
                raise ValueError("No session to get session id from")
            session_id = self._last_session_response.session_id
        return session_id

    def start(self, **data: Unpack[SessionStartRequestDict]) -> SessionResponse:
        request = SessionRequest.model_validate(data)
        response = self.request(SessionsClient.session_start_endpoint().with_request(request))
        self._last_session_response = response
        return response

    def close(self, session_id: str | None = None) -> SessionResponse:
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_close_endpoint(session_id=session_id)
        response = SessionResponse.model_validate(self.request(endpoint))
        self._last_session_response = None
        return response

    def status(self, session_id: str | None = None) -> SessionResponse:
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_status_endpoint(session_id=session_id)
        response = SessionResponse.model_validate(self.request(endpoint))
        self._last_session_response = response
        return response

    def list(self, **data: Unpack[ListRequestDict]) -> Sequence[SessionResponse]:
        params = SessionListRequest.model_validate(data)
        endpoint = SessionsClient.session_list_endpoint(params=params)
        return self.request_list(endpoint)

    def debug_info(self, session_id: str | None = None) -> SessionDebugResponse:
        session_id = self.get_session_id(session_id)
        endpoint = SessionsClient.session_debug_endpoint(session_id=session_id)
        return self.request(endpoint)

    def debug_tab_info(self, session_id: str | None = None, tab_idx: int | None = None) -> TabSessionDebugResponse:
        session_id = self.get_session_id(session_id)
        params = TabSessionDebugRequest(tab_idx=tab_idx) if tab_idx is not None else None
        endpoint = SessionsClient.session_debug_tab_endpoint(session_id=session_id, params=params)
        return self.request(endpoint)
