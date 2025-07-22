from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack

from notte_core.actions import ActionUnion
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import (
    ExecutionResponseWithSession,
    ObserveRequest,
    ObserveRequestDict,
    ObserveResponse,
    ScrapeRequest,
    ScrapeRequestDict,
    ScrapeResponse,
)

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


@final
class PageClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    PAGE_SCRAPE = "{session_id}/page/scrape"
    PAGE_OBSERVE = "{session_id}/page/observe"
    PAGE_EXECUTE = "{session_id}/page/execute"

    def __init__(
        self,
        root_client: "NotteClient",
        api_key: str | None = None,
        verbose: bool = False,
        server_url: str | None = None,
    ):
        """
        Initialize the PageClient instance.

        Configures the client with the page base endpoint for interacting with the Notte API and initializes session tracking for subsequent requests.

        Args:
            api_key: Optional API key used for authenticating API requests.
        """
        # TODO: change to page base endpoint when it's deployed
        super().__init__(
            root_client=root_client,
            base_endpoint_path="sessions",
            api_key=api_key,
            verbose=verbose,
            server_url=server_url,
        )

    @staticmethod
    def _page_scrape_endpoint(session_id: str | None = None) -> NotteEndpoint[ScrapeResponse]:
        """
        Creates a NotteEndpoint for the scrape action.

        Returns:
            NotteEndpoint[ObserveResponse]: An endpoint configured with the scrape path,
            POST method, and an expected ObserveResponse.
        """
        path = PageClient.PAGE_SCRAPE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ScrapeResponse, method="POST")

    @staticmethod
    def _page_observe_endpoint(session_id: str | None = None) -> NotteEndpoint[ObserveResponse]:
        """
        Creates a NotteEndpoint for observe operations.

        Returns:
            NotteEndpoint[ObserveResponse]: An endpoint configured with the observe path,
            using the HTTP POST method and expecting an ObserveResponse.
        """
        path = PageClient.PAGE_OBSERVE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ObserveResponse, method="POST")

    @staticmethod
    def _page_step_endpoint(session_id: str | None = None) -> NotteEndpoint[ExecutionResponseWithSession]:
        """
        Creates a NotteEndpoint for initiating a step action.

        Returns a NotteEndpoint configured with the 'POST' method using the PAGE_STEP path and expecting an ObserveResponse.
        """
        path = PageClient.PAGE_EXECUTE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ExecutionResponseWithSession, method="POST")

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """
        Returns the API endpoints for scraping, observing, and stepping actions.

        This function aggregates and returns the endpoints used by the client to perform
        scrape, observe, and step operations with the Notte API.
        """
        return [
            PageClient._page_scrape_endpoint(),
            PageClient._page_observe_endpoint(),
            PageClient._page_step_endpoint(),
        ]

    def scrape(self, session_id: str, **data: Unpack[ScrapeRequestDict]) -> ScrapeResponse:
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
        endpoint = PageClient._page_scrape_endpoint(session_id=session_id)
        response = self.request(endpoint.with_request(request))
        # Manually override the data.structured space to better match the response format
        response_format = request.response_format
        structured = response.structured
        if response_format is not None and structured is not None:
            if structured.success and structured.data is not None:
                structured.data = response_format.model_validate(structured.data.model_dump())
        return response

    def observe(self, session_id: str, **data: Unpack[ObserveRequestDict]) -> ObserveResponse:
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
        endpoint = PageClient._page_observe_endpoint(session_id=session_id)
        obs_response = self.request(endpoint.with_request(request))
        return obs_response

    def execute(self, session_id: str, action: ActionUnion) -> ExecutionResponseWithSession:
        """
        Sends a step action request and returns an ExecutionResponseWithSession.

        Validates the provided keyword arguments to ensure they conform to the step
        request schema, retrieves the step endpoint, submits the request, and transforms
        the API response into an Observation.

        Args:
            **data: Arbitrary keyword arguments matching the expected structure for a
                step request.

        Returns:
            An Observation object constructed from the API response.
        """
        endpoint = PageClient._page_step_endpoint(session_id=session_id)
        obs_response = self.request(endpoint.with_request(action))
        return obs_response
