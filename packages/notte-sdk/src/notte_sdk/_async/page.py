"""Async page endpoint client for the Notte SDK."""
# pyright: reportOverlappingOverload=false, reportUnnecessaryIsInstance=false

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Unpack, overload

from notte_core.actions import ActionUnion, CaptchaSolveAction, InteractionActionUnion
from notte_core.common.config import PerceptionType
from notte_core.common.logging import logger
from notte_core.common.telemetry import track_usage
from notte_core.data.space import ImageData, StructuredData, TBaseModel
from notte_core.errors.processing import ScrapeFailedError
from pydantic import BaseModel, RootModel
from typing_extensions import final

from notte_sdk._async.base import AsyncBaseClient, NotteEndpoint
from notte_sdk._async.http import AsyncHTTPClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import (
    ExecutionResultResponse,
    ObserveRequest,
    ObserveRequestDict,
    ObserveResponse,
    PaginationParamsDict,
    ScrapeMarkdownParamsDict,
    ScrapeRequest,
    ScrapeRequestDict,
    ScrapeResponse,
)

if TYPE_CHECKING:
    from notte_sdk._async.client import AsyncNotteClient


@final
class AsyncPageClient(AsyncBaseClient):
    """Async client for page operations."""

    # Endpoints
    PAGE_SCRAPE = "{session_id}/page/scrape"
    PAGE_OBSERVE = "{session_id}/page/observe"
    PAGE_EXECUTE = "{session_id}/page/execute"

    def __init__(
        self,
        root_client: "AsyncNotteClient",
        http_client: AsyncHTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize AsyncPageClient."""
        super().__init__(
            root_client=root_client,
            base_endpoint_path="sessions",
            http_client=http_client,
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _page_scrape_endpoint(session_id: str | None = None) -> NotteEndpoint[ScrapeResponse]:
        path = AsyncPageClient.PAGE_SCRAPE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ScrapeResponse, method="POST")

    @staticmethod
    def _page_observe_endpoint(session_id: str | None = None) -> NotteEndpoint[ObserveResponse]:
        path = AsyncPageClient.PAGE_OBSERVE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ObserveResponse, method="POST")

    @staticmethod
    def _page_execute_endpoint(session_id: str | None = None) -> NotteEndpoint[ExecutionResultResponse]:
        path = AsyncPageClient.PAGE_EXECUTE
        if session_id is not None:
            path = path.format(session_id=session_id)
        return NotteEndpoint(path=path, response=ExecutionResultResponse, method="POST")

    @overload
    async def scrape(
        self, session_id: str, /, *, raise_on_failure: bool = True, **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> str: ...

    @overload
    async def scrape(
        self,
        session_id: str,
        *,
        instructions: str,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> dict[str, Any]: ...

    @overload
    async def scrape(
        self,
        session_id: str,
        *,
        instructions: str,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[BaseModel]: ...

    @overload
    async def scrape(
        self, session_id: str, /, *, only_images: Literal[True], raise_on_failure: bool = True
    ) -> list[ImageData]: ...

    @overload
    async def scrape(
        self,
        session_id: str,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> TBaseModel: ...

    @overload
    async def scrape(
        self,
        session_id: str,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    @track_usage("cloud.session.scrape")
    async def scrape(
        self, session_id: str, *, raise_on_failure: bool = True, **data: Unpack[ScrapeRequestDict]
    ) -> StructuredData[BaseModel] | BaseModel | dict[str, Any] | str | list[ImageData]:
        """Scrape a page."""
        request = ScrapeRequest.model_validate(data)
        endpoint = AsyncPageClient._page_scrape_endpoint(session_id=session_id)
        response = await self.request(endpoint.with_request(request))

        # Handle images scraping
        if request.only_images and response.images is not None:
            return response.images

        # Handle structured data scraping
        structured = response.structured
        if request.requires_schema():
            if structured is None:
                error_message = "Failed to scrape structured data. This should not happen. Please report this issue."
                if raise_on_failure:
                    raise ScrapeFailedError(error_message)
                return StructuredData[BaseModel](success=False, error=error_message, data=None)

            if raise_on_failure:
                extracted_data = structured.get()
                if request.response_format is not None:
                    extracted_data_dict = (
                        extracted_data.model_dump() if isinstance(extracted_data, BaseModel) else extracted_data
                    )
                    extracted_data = request.response_format.model_validate(extracted_data_dict)
                return extracted_data

            if isinstance(structured.data, RootModel):
                structured.data = structured.data.root  # type: ignore[attr-defined]
            if request.response_format is not None and structured.data is not None:
                structured.data = request.response_format.model_validate(structured.data)
            return structured

        return response.markdown

    @overload
    async def observe(
        self,
        session_id: str,
        *,
        instructions: str,
        url: str | None = None,
        perception_type: PerceptionType | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> list[InteractionActionUnion]: ...

    @overload
    async def observe(
        self,
        session_id: str,
        *,
        instructions: None = None,
        url: str | None = None,
        perception_type: PerceptionType | None = None,
        **pagination: Unpack[PaginationParamsDict],
    ) -> ObserveResponse: ...

    @track_usage("cloud.session.observe")
    async def observe(
        self, session_id: str, **data: Unpack[ObserveRequestDict]
    ) -> ObserveResponse | list[InteractionActionUnion]:
        """Observe a page."""
        instructions = data.get("instructions")
        request = ObserveRequest.model_validate(data)
        endpoint = AsyncPageClient._page_observe_endpoint(session_id=session_id)
        obs_response = await self.request(endpoint.with_request(request))
        if instructions is not None:
            return list(obs_response.space.interaction_actions)
        return obs_response

    @track_usage("cloud.session.execute")
    async def execute(self, session_id: str, action: ActionUnion) -> ExecutionResultResponse:
        """Execute an action on the page."""
        endpoint = AsyncPageClient._page_execute_endpoint(session_id=session_id)
        is_captcha = isinstance(action, CaptchaSolveAction)
        request_timeout = 100 if is_captcha else self.DEFAULT_REQUEST_TIMEOUT_SECONDS

        for _ in range(3):
            try:
                obs_response = await self.request(endpoint.with_request(action), timeout=request_timeout)
                return obs_response
            except NotteAPIError as e:
                if e.status_code == 408 and is_captcha:
                    logger.warning(
                        "Solve captcha action timed out. This can happen for long and complex captchas. Retrying..."
                    )
                    continue
                raise e

        raise ValueError(f"Failed to execute action '{action.type}'. This should not happen. Please report this issue.")
