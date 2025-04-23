from collections.abc import Sequence
from typing import TypeVar, Unpack

from notte_core.actions.space import ActionSpace
from notte_core.browser.observation import Observation
from notte_core.controller.space import SpaceCategory
from notte_core.data.space import DataSpace
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.errors import InvalidRequestError
from notte_sdk.types import (
    ObserveRequest,
    ObserveRequestDict,
    ObserveResponse,
    ScrapeRequest,
    ScrapeRequestDict,
    SessionRequest,
    StepRequest,
    StepRequestDict,
)

TSessionRequestDict = TypeVar("TSessionRequestDict", bound=SessionRequest)


@final
class PageClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    PAGE_SCRAPE = "scrape"
    PAGE_OBSERVE = "observe"
    PAGE_STEP = "step"

    def __init__(
        self,
        api_key: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize the PageClient instance.

        Configures the client with the page base endpoint for interacting with the Notte API and initializes session tracking for subsequent requests.

        Args:
            api_key: Optional API key used for authenticating API requests.
        """
        # TODO: change to page base endpoint when it's deployed
        super().__init__(base_endpoint_path="env", api_key=api_key, verbose=verbose)

    @staticmethod
    def page_scrape_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Creates a NotteEndpoint for the scrape action.

        Returns:
            NotteEndpoint[ObserveResponse]: An endpoint configured with the scrape path,
            POST method, and an expected ObserveResponse.
        """
        return NotteEndpoint(path=PageClient.PAGE_SCRAPE, response=ObserveResponse, method="POST")

    @staticmethod
    def page_observe_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Creates a NotteEndpoint for observe operations.

        Returns:
            NotteEndpoint[ObserveResponse]: An endpoint configured with the observe path,
            using the HTTP POST method and expecting an ObserveResponse.
        """
        return NotteEndpoint(path=PageClient.PAGE_OBSERVE, response=ObserveResponse, method="POST")

    @staticmethod
    def page_step_endpoint() -> NotteEndpoint[ObserveResponse]:
        """
        Creates a NotteEndpoint for initiating a step action.

        Returns a NotteEndpoint configured with the 'POST' method using the PAGE_STEP path and expecting an ObserveResponse.
        """
        return NotteEndpoint(path=PageClient.PAGE_STEP, response=ObserveResponse, method="POST")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """
        Returns the API endpoints for scraping, observing, and stepping actions.

        This function aggregates and returns the endpoints used by the client to perform
        scrape, observe, and step operations with the Notte API.
        """
        return [
            PageClient.page_scrape_endpoint(),
            PageClient.page_observe_endpoint(),
            PageClient.page_step_endpoint(),
        ]

    def scrape(self, **data: Unpack[ScrapeRequestDict]) -> DataSpace:
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
        endpoint = PageClient.page_scrape_endpoint()
        obs_response = self.request(endpoint.with_request(request))
        obs = self._format_observe_response(obs_response)
        if obs.data is None:
            raise ValueError("No data returned from scrape")
        scraped_data = obs.data
        # Manually override the data.structured space to better match the response format
        response_format = request.response_format
        if response_format is not None and scraped_data.structured is not None:
            if scraped_data.structured.success and scraped_data.structured.data is not None:
                scraped_data.structured.data = response_format.model_validate(scraped_data.structured.data.model_dump())
        return scraped_data

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
        endpoint = PageClient.page_observe_endpoint()
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
        endpoint = PageClient.page_step_endpoint()
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
