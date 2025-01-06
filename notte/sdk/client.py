import os
from typing import Any, ClassVar, Unpack

import requests
from loguru import logger
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

    DEFAULT_SERVER_URL: ClassVar[str] = "https://api.notte.cc"

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
    ):
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
        if data is not None and data.get("session_id") is None and self.session_id is not None:
            logger.info(f"Using session_id: {self.session_id}")
            data["session_id"] = self.session_id
        response = requests.post(f"{self.server_url}/{path}", headers=headers, json=data)
        # check common errors
        if response.status_code != 200:
            raise ValueError(response.json())
        return response.json()  # type:ignore

    def start(self, **data: Unpack[SessionRequestDict]) -> SessionResponse:
        if self.session_id is not None:
            logger.warning("Session already started. Closing it before starting a new one.")
            _ = self.close()
        request = SessionRequest(**data)
        response = SessionResponse.model_validate(self._request("session/start", request.model_dump()))  # type:ignore
        self.session_id = response.session_id
        return response

    def close(self, **data: Unpack[SessionRequestDict]) -> SessionResponse:
        request = SessionRequest(**data)
        response = SessionResponse.model_validate(self._request("session/close", request.model_dump()))  # type:ignore
        self.session_id = None
        return response

    def __enter__(self) -> "NotteClient":
        _ = self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        _ = self.close()

    def _format_observe_response(self, response_dict: dict[str, Any]) -> Observation:
        if response_dict.get("status") not in [200, None] or "detail" in response_dict:
            raise ValueError(response_dict)
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
