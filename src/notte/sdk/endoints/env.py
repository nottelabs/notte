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
        """
        Initializes the EnvClient instance.
        
        Configures the base endpoint for environmental interactions with the Notte API.
        Optional API credentials and server URL can be provided to customize authentication
        and connection settings. Also sets up internal state to track the last session response.
         
        Args:
            api_key (str or None): Optional API key used for authenticating API requests.
            server_url (str or None): Optional URL of the Notte API server.
        """
        super().__init__(base_endpoint_path="env", api_key=api_key, server_url=server_url)
        self._last_session_response: SessionResponse | None = None

    @staticmethod
    def env_scrape_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Returns a NotteEndpoint configured for the scrape action.
        
        This endpoint is preconfigured with the scrape path defined in EnvClient.ENV_SCRAPE, an expected response model of ObserveResponse, and the HTTP POST method.
        """
        return NotteEndpoint(path=EnvClient.ENV_SCRAPE, response=ObserveResponse, method="POST")

    @staticmethod
    def env_observe_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Create and return a NotteEndpoint for the observe action.
        
        The endpoint uses the observe path defined in EnvClient, employs the POST HTTP method, and
        is configured to expect an ObserveResponse.
        """
        return NotteEndpoint(path=EnvClient.ENV_OBSERVE, response=ObserveResponse, method="POST")

    @staticmethod
    def env_step_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Constructs a NotteEndpoint for step operations.
        
        Returns a NotteEndpoint configured to send POST requests to the step endpoint using
        the step path from EnvClient and expect responses formatted as an ObserveResponse.
        """
        return NotteEndpoint(path=EnvClient.ENV_STEP, response=ObserveResponse, method="POST")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """
        Returns a sequence of endpoints for environment API actions.
        
        This function aggregates the endpoints for scraping, observing, and stepping sessions provided by EnvClient.
        
        Returns:
            Sequence[NotteEndpoint[BaseModel]]: A list of endpoints for the environment actions.
        """
        return [
            EnvClient.env_scrape_endpoint(),
            EnvClient.env_observe_endpoint(),
            EnvClient.env_step_endpoint(),
        ]

    @property
    def session_id(self) -> str | None:
        """
        Returns the session identifier from the last session response.
        
        If no session response is available, returns None.
        """
        return self._last_session_response.session_id if self._last_session_response is not None else None

    def get_session_id(self, session_id: str | None = None) -> str:
        """
        Retrieves the active session ID.
        
        If a session ID is provided, it is returned directly; otherwise, the method returns
        the session ID from the last session response. Raises a ValueError if no session ID
        is available.
        """
        if session_id is None:
            if self._last_session_response is None:
                raise ValueError("No session to get session id from")
            session_id = self._last_session_response.session_id
        return session_id

    def scrape(self, **data: Unpack[ScrapeRequestDict]) -> Observation:
        """
        Scrape a page using the Notte API.
        
        Validates keyword arguments against the ScrapeRequest model and sends a scraping
        request to the corresponding endpoint. Either a URL or a session ID must be provided;
        otherwise, an InvalidRequestError is raised. Returns an Observation object
        constructed from the response.
          
        Args:
            **data: Arbitrary keyword arguments for the scraping request. These must include
                   either a 'url' for a new scrape or a 'session_id' corresponding to an existing session.
          
        Returns:
            Observation: An object encapsulating the scraped response data.
          
        Raises:
            InvalidRequestError: If neither a 'url' nor a 'session_id' is provided.
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
        Sends an observe request and returns a formatted observation.
        
        Validates the observe request parameters using the ObserveRequest model and ensures that
        either a session_id or a URL is provided. If both are absent, an InvalidRequestError is raised.
        The request is sent to the observe endpoint, and the response is formatted into an Observation.
        
        Args:
            **data: Keyword arguments conforming to the ObserveRequest model. Must include
                    at least a session_id or a URL.
        
        Returns:
            Observation: The formatted observation derived from the API response.
        
        Raises:
            InvalidRequestError: If neither a session_id nor a URL is provided.
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
        Sends a step request to the Notte API and returns an observation.
        
        Validates the provided data against the step request schema, dispatches the request to the
        step endpoint, and formats the API response into an Observation.
        """
        request = StepRequest.model_validate(data)
        endpoint = EnvClient.env_step_endpoint()
        obs_response = self.request(endpoint.with_request(request))
        return self._format_observe_response(obs_response)

    def _format_observe_response(self, response: ObserveResponse) -> Observation:
        """
        Formats an observe response into an Observation.
        
        Updates the client's last session response with data from the response and constructs an
        Observation containing metadata, screenshot, and details for action and data spaces. If the
        response's space or data fields are absent, the corresponding Observation attributes will be None.
        
        Args:
            response: An ObserveResponse containing data from an observe API call.
        
        Returns:
            An Observation object derived from the provided response.
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
