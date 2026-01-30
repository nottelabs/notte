from typing import TYPE_CHECKING, Literal, Unpack, overload

from notte_core.actions import ActionUnion, CaptchaSolveAction
from notte_core.common.logging import logger
from notte_core.common.telemetry import track_usage
from notte_core.data.space import ImageData, TBaseModel
from pydantic import BaseModel
from typing_extensions import final

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import (
    ExecutionResponseWithSession,
    ObserveRequest,
    ObserveRequestDict,
    ObserveResponse,
    ScrapeMarkdownParamsDict,
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
    def _page_execute_endpoint(session_id: str | None = None) -> NotteEndpoint[ExecutionResponseWithSession]:
        """
        Creates a NotteEndpoint for initiating a step action.

        Returns a NotteEndpoint configured with the 'POST' method using the PAGE_STEP path and expecting an ObserveResponse.
        """
        path = PageClient.PAGE_EXECUTE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ExecutionResponseWithSession, method="POST")

    @overload
    def scrape(
        self, session_id: str, /, *, raise_on_failure: bool = True, **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> str: ...

    @overload
    def scrape(
        self,
        session_id: str,
        *,
        instructions: str,
        raise_on_failure: bool = True,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> BaseModel: ...

    @overload
    def scrape(
        self, session_id: str, *, only_images: Literal[True], raise_on_failure: bool = True
    ) -> list[ImageData]: ...

    @overload
    def scrape(
        self,
        session_id: str,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: bool = True,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> TBaseModel: ...

    @track_usage("cloud.session.scrape")
    def scrape(
        self, session_id: str, *, raise_on_failure: bool = True, **data: Unpack[ScrapeRequestDict]
    ) -> str | BaseModel | list[ImageData]:
        """
        Scrapes a page using provided parameters via the Notte API.

        Validates the scraped request data to ensure that either a URL or session ID is provided.
        If both are omitted, raises an InvalidRequestError. The request is sent to the configured
        scrape endpoint and the resulting response is formatted into an Observation object.

        Args:
            session_id: The session ID to scrape from.
            raise_on_failure: If True (default), raises ScrapeFailedError when structured data
                extraction fails. If False, returns the StructuredData with success=False.
            **data: Arbitrary keyword arguments validated against ScrapeRequestDict.

        Returns:
            When using instructions/response_format and raise_on_failure=True: returns the extracted data directly.
            When raise_on_failure=False: returns StructuredData wrapper so user can check .success.
            For markdown scraping: returns str.
            For image scraping: returns list[ImageData].

        Raises:
            ScrapeFailedError: If structured data extraction fails and raise_on_failure=True.
        """
        request = ScrapeRequest.model_validate(data)
        endpoint = PageClient._page_scrape_endpoint(session_id=session_id)
        response = self.request(endpoint.with_request(request))
        # Handle images scraping
        if request.only_images and response.images is not None:
            return response.images
        # Handle structured data scraping
        structured = response.structured
        if request.requires_schema():
            if structured is None:
                raise ValueError("Failed to scrape structured data. This should not happen. Please report this issue.")
            # Use structured.get() which raises ScrapeFailedError if failed, and unwraps RootModel
            if raise_on_failure:
                extracted_data = structured.get()
                # Validate against response_format if provided
                if request.response_format is not None:
                    extracted_data = request.response_format.model_validate(extracted_data.model_dump())
                return extracted_data
            return structured
        return response.markdown

    @track_usage("cloud.session.observe")
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

    @track_usage("cloud.session.execute")
    def execute(self, session_id: str, action: ActionUnion) -> ExecutionResponseWithSession:
        """
        Sends a step action request and returns an ExecutionResponseWithSession.

        Validates the provided keyword arguments to ensure they conform to the step
        request schema, retrieves the step endpoint, submits the request, and transforms
        the API response into an Observation.

        Args:
            session_id: The session ID to execute the action on.
            action: The action to execute. For InteractionActions, the timeout can be set
                directly on the action object via the `timeout` field.

        Returns:
            An Observation object constructed from the API response.
        """
        endpoint = PageClient._page_execute_endpoint(session_id=session_id)
        is_captcha = isinstance(action, CaptchaSolveAction)
        request_timeout = 100 if is_captcha else self.DEFAULT_REQUEST_TIMEOUT_SECONDS

        for _ in range(3):
            try:
                obs_response = self.request(endpoint.with_request(action), timeout=request_timeout)
                return obs_response
            except NotteAPIError as e:
                if e.status_code == 408 and is_captcha:
                    logger.warning(
                        "Solve captcha action timed out. This can happen for long and complex captchas. Retrying..."
                    )
                    continue
                raise e
        raise ValueError(f"Failed to execute action '{action.type}'. This should not happen. Please report this issue.")
