import os
from typing import Any, ClassVar, Unpack

import requests
from typing_extensions import final

from notte.actions.space import ActionSpace, SpaceCategory
from notte.browser.observation import Observation
from notte.sdk.types import (
    ObserveRequest,
    ObserveRequestDict,
    ObserveResponse,
    SessionRequest,
    SessionRequestDict,
    SessionResponse,
    StepRequest,
    StepRequestDict,
)


@final
class NotteClient:
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    DEFAULT_SERVER_URL: ClassVar[str] = "https://api.notte.cc/v1"

    def __init__(self, api_key: str | None = None, server_url: str | None = None):
        self.token = api_key or os.getenv("NOTTE_API_KEY")
        if self.token is None:
            raise ValueError("NOTTE_API_KEY needs to be provided")
        self.server_url = server_url or self.DEFAULT_SERVER_URL
        self.session_id: str | None = None

    def _request(
        self,
        path: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.post(f"{self.server_url}/{path}", headers=headers, json=data)
        return response.json()  # type:ignore

    def create_session(self, **data: Unpack[SessionRequestDict]) -> SessionResponse:
        request = SessionRequest(**data)
        response = SessionResponse.model_validate(self._request("session/create", request.model_dump()))  # type:ignore
        self.session_id = response.session_id
        return response

    def close_session(self, **data: Unpack[SessionRequestDict]) -> SessionResponse:
        request = SessionRequest(**data)
        response = SessionResponse.model_validate(self._request("session/close", request.model_dump()))  # type:ignore
        self.session_id = None
        return response

    def _format_observe_response(self, response_dict: dict[str, Any]) -> Observation:
        response = ObserveResponse.model_validate(response_dict)
        self.session_id = response.session_id
        # TODO: add title and description
        return Observation(
            title=response.title,
            url=response.url,
            timestamp=response.timestamp,
            screenshot=response.screenshot,
            _space=(
                None
                if response.space is None
                else ActionSpace(
                    description=response.space.description,
                    category=SpaceCategory(response.space.category),
                    _actions=response.space.actions,
                )
            ),
            data=response.data,
        )

    def scrape(self, **data: Unpack[ObserveRequestDict]) -> Observation:
        request = ObserveRequest(**data)
        if request.session_id is None and request.url is None:
            raise ValueError("Either url or session_id needs to be provided")
        response_dict = self._request("env/scrape", request.model_dump())  # type:ignore
        return self._format_observe_response(response_dict)

    def observe(self, **data: Unpack[ObserveRequestDict]) -> Observation:
        request = ObserveRequest(**data)
        response_dict = self._request("env/observe", request.model_dump())  # type:ignore
        return self._format_observe_response(response_dict)

    def step(self, **data: Unpack[StepRequestDict]) -> Observation:
        request = StepRequest(**data)
        response_dict = self._request(
            "env/step",
            request.model_dump(),
        )  # type:ignore
        return self._format_observe_response(response_dict)
