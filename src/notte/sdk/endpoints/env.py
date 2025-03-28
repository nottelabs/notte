from collections.abc import Sequence
from typing import TypeVar, Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte.actions.space import ActionSpace
from notte.browser.observation import Observation
from notte.controller.space import SpaceCategory
from notte.data.space import DataSpace
from notte.errors.sdk import InvalidRequestError
from notte.sdk.endpoints.base import BaseClient, NotteEndpoint
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
    ):
        """
        Initialize the EnvClient instance.

        Configures the client with the environment base endpoint for interacting with the Notte API and initializes session tracking for subsequent requests.

        Args:
            api_key: Optional API key used for authenticating API requests.
        """
        super().__init__(base_endpoint_path="env", api_key=api_key)
        self._last_session_response: SessionResponse | None = None

    @staticmethod
    def env_scrape_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Creates a NotteEndpoint for the scrape action.

        Returns:
            NotteEndpoint[ObserveResponse]: An endpoint configured with the scrape path,
            POST method, and an expected ObserveResponse.
        """
        return NotteEndpoint(path=EnvClient.ENV_SCRAPE, response=ObserveResponse, method="POST")

    @staticmethod
    def env_observe_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Creates a NotteEndpoint for observe operations.

        Returns:
            NotteEndpoint[ObserveResponse]: An endpoint configured with the observe path,
            using the HTTP POST method and expecting an ObserveResponse.
        """
        return NotteEndpoint(path=EnvClient.ENV_OBSERVE, response=ObserveResponse, method="POST")

    @staticmethod
    def env_step_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Creates a NotteEndpoint for initiating a step action.

        Returns a NotteEndpoint configured with the 'POST' method using the ENV_STEP path and expecting an ObserveResponse.
        """
        return NotteEndpoint(path=EnvClient.ENV_STEP, response=ObserveResponse, method="POST")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """
        Returns the API endpoints for scraping, observing, and stepping actions.

        This function aggregates and returns the endpoints used by the client to perform
        scrape, observe, and step operations with the Notte API.
        """
        return [
            EnvClient.env_scrape_endpoint(),
            EnvClient.env_observe_endpoint(),
            EnvClient.env_step_endpoint(),
        ]

    @property
    def session_id(self) -> str | None:
        """
        Returns the session ID from the last session response.

        If no session response exists, returns None.
        """
        return self._last_session_response.session_id if self._last_session_response is not None else None

    def get_session_id(self, session_id: str | None = None) -> str:
        """
        Retrieves the session ID for the current session.

        If an explicit session ID is provided, it is returned. Otherwise, the method extracts
        the session ID from the most recent session response. A ValueError is raised if no
        session ID is available.

        Args:
            session_id: Optional explicit session identifier. If None, the last session's ID is used.

        Returns:
            The session identifier.

        Raises:
            ValueError: If no session ID can be retrieved.
        """
        if session_id is None:
            if self._last_session_response is None:
                raise InvalidRequestError("No session to get session id from")
            session_id = self._last_session_response.session_id
        return session_id

    def scrape(self, **data: Unpack[ScrapeRequestDict]) -> Observation:
        """
        Scrapes a page using provided parameters via the Notte API.

        Validates the scraped request data to ensure that either a URL or session ID is provided.
        If both are omitted, raises an InvalidRequestError. The request is sent to the configured
        scrape endpoint and the resulting response is formatted into an Observation object.

        Args:
            **data: Arbitrary keyword arguments validated against ScrapeRequestDict,
                   expecting at least one of 'url' or 'session_id'.

        Returns:
            An Observation object containing metadata, screenshot, action space, and data space.

        Raises:
            InvalidRequestError: If neither 'url' nor 'session_id' is supplied.
        """
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
        """
        Observes a page via the Notte API.

        Constructs and validates an observation request from the provided keyword arguments.
        Either a 'url' or a 'session_id' must be supplied; otherwise, an InvalidRequestError is raised.
        The request is sent to the observe endpoint, and the response is formatted into an Observation object.

        Parameters:
            **data: Arbitrary keyword arguments corresponding to observation request fields.
                    At least one of 'url' or 'session_id' must be provided.

        Returns:
            Observation: The formatted observation result from the API response.
        """
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
        """
        Sends a step action request and returns an Observation.

        Validates the provided keyword arguments to ensure they conform to the step
        request schema, retrieves the step endpoint, submits the request, and transforms
        the API response into an Observation.

        Args:
            **data: Arbitrary keyword arguments matching the expected structure for a
                step request.

        Returns:
            An Observation object constructed from the API response.
        """
        request = StepRequest.model_validate(data)
        endpoint = EnvClient.env_step_endpoint()
        obs_response = self.request(endpoint.with_request(request))
        return self._format_observe_response(obs_response)

    def _format_observe_response(self, response: ObserveResponse) -> Observation:
        """
        Formats an observe response into an Observation object.

        Extracts session information from the provided response to update the client's last session state
        and constructs an Observation using response metadata and screenshot. If the response does not include
        space or data details, those Observation attributes are set to None; otherwise, they are converted into
        an ActionSpace or DataSpace instance respectively.

        Args:
            response: An ObserveResponse object containing session, metadata, screenshot, space, and data.

        Returns:
            An Observation object representing the formatted response.
        """
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
