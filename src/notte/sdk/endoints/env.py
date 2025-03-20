from collections.abc import Sequence
from typing import TypeVar, Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte.actions.space import ActionSpace
from notte.browser.observation import Observation
from notte.controller.space import SpaceCategory
from notte.data.space import DataSpace
from notte.errors.sdk import InvalidRequestError
from notte.sdk.endoints.base import BaseClient, NotteEndpoint
from notte.sdk.types import (
    ObserveRequest,
    ObserveRequestDict,
    ObserveResponse,
    ScrapeRequest,
    ScrapeRequestDict,
    SessionRequestDict,
    SessionResponse,
    StepRequest,
    StepRequestDict,
)

TSessionRequestDict = TypeVar("TSessionRequestDict", bound=SessionRequestDict)


@final
class EnvClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    ENV_SCRAPE = "scrape"
    ENV_OBSERVE = "observe"
    ENV_STEP = "step"

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
    ):
        super().__init__(base_endpoint_path="env", api_key=api_key, server_url=server_url)
        self._last_session_response: SessionResponse | None = None

    @staticmethod
    def env_scrape_endpoint() -> NotteEndpoint[ObserveResponse]:
        return NotteEndpoint(path=EnvClient.ENV_SCRAPE, response=ObserveResponse, method="POST")

    @staticmethod
    def env_observe_endpoint() -> NotteEndpoint[ObserveResponse]:
        return NotteEndpoint(path=EnvClient.ENV_OBSERVE, response=ObserveResponse, method="POST")

    @staticmethod
    def env_step_endpoint() -> NotteEndpoint[ObserveResponse]:
        return NotteEndpoint(path=EnvClient.ENV_STEP, response=ObserveResponse, method="POST")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        return [
            EnvClient.env_scrape_endpoint(),
            EnvClient.env_observe_endpoint(),
            EnvClient.env_step_endpoint(),
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

    def scrape(self, **data: Unpack[ScrapeRequestDict]) -> Observation:
        request = ScrapeRequest.model_validate(data)
        if request.session_id is None and request.url is None:
            raise InvalidRequestError(
                (
                    "Either url or session_id needs to be provided to scrape a page, "
                    "e.g `await client.scrape(url='https://www.google.com')`"
                )
            )
        endpoint = EnvClient.env_scrape_endpoint()
        obs_response = self.request(endpoint.with_request(request))
        return self._format_observe_response(obs_response)

    def observe(self, **data: Unpack[ObserveRequestDict]) -> Observation:
        request = ObserveRequest.model_validate(data)
        if request.session_id is None and request.url is None:
            raise InvalidRequestError(
                (
                    "Either url or session_id needs to be provided to scrape a page, "
                    "e.g `await client.scrape(url='https://www.google.com')`"
                )
            )
        endpoint = EnvClient.env_observe_endpoint()
        obs_response = self.request(endpoint.with_request(request))
        return self._format_observe_response(obs_response)

    def step(self, **data: Unpack[StepRequestDict]) -> Observation:
        request = StepRequest.model_validate(data)
        endpoint = EnvClient.env_step_endpoint()
        obs_response = self.request(endpoint.with_request(request))
        return self._format_observe_response(obs_response)

    def _format_observe_response(self, response: ObserveResponse) -> Observation:
        self._last_session_response = response.session
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
