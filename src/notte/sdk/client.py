import os
from typing import Any, ClassVar, TypeVar, Unpack

import requests
from loguru import logger
from typing_extensions import final

from notte.actions.space import ActionSpace
from notte.browser.observation import Observation
from notte.controller.space import SpaceCategory
from notte.data.space import DataSpace
from notte.errors.sdk import AuthenticationError, InvalidRequestError, NotteAPIError
from notte.sdk.types import (
    ObserveRequest,
    ObserveRequestDict,
    ObserveResponse,
    ScrapeRequest,
    ScrapeRequestDict,
    SessionRequest,
    SessionRequestDict,
    SessionResponse,
    StepRequest,
    StepRequestDict,
)

TSessionRequestDict = TypeVar("TSessionRequestDict", bound=SessionRequestDict)


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
            raise AuthenticationError("NOTTE_API_KEY needs to be provided")
        self.server_url = server_url or self.DEFAULT_SERVER_URL
        self._base_session_request: SessionRequest | None = None

    @property
    def session_id(self) -> str | None:
        return self._base_session_request.session_id if self._base_session_request is not None else None

    @session_id.setter
    def session_id(self, value: str | None) -> None:
        if self._base_session_request is not None:
            self._base_session_request.session_id = value

    def _request(self, path: str, request: SessionRequest) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        data = request.model_dump()
        logger.info(
            f"Request to `{path}` with {', '.join([f'{k}={data[k]}' for k in SessionRequest.model_fields.keys()])}"
        )
        response = requests.post(f"{self.server_url}/{path}", headers=headers, json=data)
        # check common errors
        response_dict: dict[str, Any] = response.json()
        if response.status_code != 200 or "detail" in response_dict:
            raise NotteAPIError(path=path, response=response)
        return response_dict

    def _format_session_args(self, data: TSessionRequestDict) -> TSessionRequestDict:
        if self._base_session_request is not None:
            args = self._base_session_request.model_dump()
            for session_arg in args.keys():
                if session_arg not in data:
                    data[session_arg] = args[session_arg]
        return data

    def start(self, **data: Unpack[SessionRequestDict]) -> SessionResponse:
        if self._base_session_request is not None and self._base_session_request.session_id is not None:
            logger.warning("One Notte session already exists. Closing it before starting a new one...")
            _ = self.close()
        if "keep_alive" not in data:
            logger.info(
                (
                    "Overriding 'keep_alive' to True to allow the session to be reused. "
                    "Please set it explicitly to `false` in `client.start()` if you want to disable this behavior."
                )
            )
            data["keep_alive"] = True
        self._base_session_request = SessionRequest(**data)
        request = SessionRequest(**self._format_session_args(data))
        response = SessionResponse.model_validate(self._request("session/start", request))
        self.session_id = response.session_id
        return response

    def close(self, **data: Unpack[SessionRequestDict]) -> SessionResponse:
        request = SessionRequest(**self._format_session_args(data))
        response = SessionResponse.model_validate(self._request("session/close", request))
        self.session_id = None
        return response

    def __enter__(self) -> "NotteClient":
        _ = self.start()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        _ = self.close()

    def _format_observe_response(self, response_dict: dict[str, Any]) -> Observation:
        if response_dict.get("status") not in [200, None] or "detail" in response_dict:
            # should never reach this point
            raise ValueError(response_dict)
        response = ObserveResponse.model_validate(response_dict)
        self.session_id = response.session.session_id
        return Observation(
            metadata=response.metadata,
            screenshot=response.screenshot,
            space=(
                None
                if response.space is None
                else ActionSpace(
                    description=response.space.description,
                    raw_actions=response.space.actions,
                    category=None if response.space.category is None else SpaceCategory(response.space.category),
                    _embeddings=None,
                )
            ),
            data=(
                None
                if response.data is None
                else DataSpace(
                    markdown=response.data.markdown,
                    images=(None if response.data.images is None else response.data.images),
                    structured=None if response.data.structured is None else response.data.structured,
                )
            ),
        )

    def scrape(self, **data: Unpack[ScrapeRequestDict]) -> Observation:
        request = ScrapeRequest(**self._format_session_args(data))
        if request.session_id is None and request.url is None:
            raise InvalidRequestError(
                (
                    "Either url or session_id needs to be provided to scrape a page, "
                    "e.g `await client.scrape(url='https://www.google.com')`"
                )
            )
        response_dict = self._request("env/scrape", request)
        return self._format_observe_response(response_dict)

    def observe(self, **data: Unpack[ObserveRequestDict]) -> Observation:
        request = ObserveRequest(**self._format_session_args(data))
        if request.session_id is None and request.url is None:
            raise InvalidRequestError(
                (
                    "Either url or session_id needs to be provided to scrape a page, "
                    "e.g `await client.scrape(url='https://www.google.com')`"
                )
            )
        response_dict = self._request("env/observe", request)
        return self._format_observe_response(response_dict)

    def step(self, **data: Unpack[StepRequestDict]) -> Observation:
        request = StepRequest(**self._format_session_args(data))
        response_dict = self._request("env/step", request)
        return self._format_observe_response(response_dict)
