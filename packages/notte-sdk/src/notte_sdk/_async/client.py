"""Async client for the Notte SDK."""
# pyright: reportImportCycles=false, reportOverlappingOverload=false

from __future__ import annotations

import os
from functools import partial
from typing import Any, Literal, Unpack, cast, overload

from notte_core.actions import GotoAction
from notte_core.common.config import LlmModel
from notte_core.common.logging import logger
from notte_core.data.space import ImageData, StructuredData, TBaseModel
from pydantic import BaseModel
from typing_extensions import final

from notte_sdk._async.agent_fallback import AsyncRemoteAgentFallback
from notte_sdk._async.agents import AsyncAgentsClient, AsyncBatchRemoteAgent, AsyncRemoteAgent
from notte_sdk._async.files import AsyncFileStorageClient, AsyncRemoteFileStorage
from notte_sdk._async.http import AsyncHTTPClient
from notte_sdk._async.personas import AsyncNottePersona, AsyncPersonasClient
from notte_sdk._async.profiles import AsyncProfilesClient
from notte_sdk._async.sessions import (
    AsyncRemoteSession,
    AsyncSessionsClient,
    SessionViewerType,
)
from notte_sdk._async.vaults import AsyncNotteVault, AsyncVaultsClient
from notte_sdk._async.workflows import AsyncNotteFunction, AsyncRemoteWorkflow, AsyncWorkflowsClient
from notte_sdk.errors import AuthenticationError
from notte_sdk.types import ScrapeMarkdownParamsDict, ScrapeRequestDict


@final
class AsyncNotteClient:
    """Async client for the Notte API.

    Example:
        ```python
        async with AsyncNotteClient() as client:
            async with client.Session() as session:
                await session.execute(type="goto", url="https://www.notte.cc")
                markdown = await session.scrape()
        ```
    """

    DEFAULT_NOTTE_API_URL = "https://api.notte.cc"

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
        viewer_type: SessionViewerType = SessionViewerType.BROWSER,
    ):
        """Initialize an AsyncNotteClient instance.

        Args:
            api_key: Optional API key for authentication (defaults to NOTTE_API_KEY env var).
            server_url: Optional server URL (defaults to NOTTE_API_URL env var or https://api.notte.cc).
            verbose: Whether to enable verbose logging.
            viewer_type: The type of viewer to use for sessions.
        """
        token = api_key or os.getenv("NOTTE_API_KEY")
        if token is None:
            raise AuthenticationError("NOTTE_API_KEY needs to be provided")

        self._api_key = token
        self._server_url = server_url or os.getenv("NOTTE_API_URL") or self.DEFAULT_NOTTE_API_URL
        self._verbose = verbose
        self._viewer_type = viewer_type

        # Create shared HTTP client
        self._http = AsyncHTTPClient(
            token=self._api_key,
            base_url=self._server_url,
        )

        # Initialize endpoint clients
        self.sessions: AsyncSessionsClient = AsyncSessionsClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
            viewer_type=viewer_type,
        )
        self.agents: AsyncAgentsClient = AsyncAgentsClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.personas: AsyncPersonasClient = AsyncPersonasClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.vaults: AsyncVaultsClient = AsyncVaultsClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.profiles: AsyncProfilesClient = AsyncProfilesClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.files: AsyncFileStorageClient = AsyncFileStorageClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.workflows: AsyncWorkflowsClient = AsyncWorkflowsClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )

        # Alias
        self.functions = self.workflows

        if self._server_url != self.DEFAULT_NOTTE_API_URL:
            logger.warning(f"NOTTE_API_URL is set to: {self._server_url}")

    async def __aenter__(self) -> "AsyncNotteClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit - close the HTTP client."""
        await self._http.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

    @property
    def models(self) -> type[LlmModel]:
        return LlmModel

    @property
    def Session(self) -> type[AsyncRemoteSession]:
        """Create an AsyncRemoteSession factory bound to this client."""
        return cast(type[AsyncRemoteSession], partial(AsyncRemoteSession, _client=self.sessions))

    @property
    def Vault(self) -> type[AsyncNotteVault]:
        """Create an AsyncNotteVault factory bound to this client."""
        return cast(type[AsyncNotteVault], partial(AsyncNotteVault, _client=self.vaults))

    @property
    def Persona(self) -> type[AsyncNottePersona]:
        """Create an AsyncNottePersona factory bound to this client."""
        return cast(type[AsyncNottePersona], partial(AsyncNottePersona, _client=self))

    @property
    def FileStorage(self) -> type[AsyncRemoteFileStorage]:
        """Create an AsyncRemoteFileStorage factory bound to this client."""
        return cast(type[AsyncRemoteFileStorage], partial(AsyncRemoteFileStorage, _client=self.files))

    @property
    def Agent(self) -> type[AsyncRemoteAgent]:
        """Create an AsyncRemoteAgent factory bound to this client."""
        return cast(type[AsyncRemoteAgent], partial(AsyncRemoteAgent, _client=self.agents))

    @property
    def BatchAgent(self) -> type[AsyncBatchRemoteAgent]:
        """Create an AsyncBatchRemoteAgent factory bound to this client."""
        return cast(type[AsyncBatchRemoteAgent], partial(AsyncBatchRemoteAgent, _client=self))

    @property
    def Workflow(self) -> type[AsyncRemoteWorkflow]:
        """Create an AsyncRemoteWorkflow factory bound to this client."""
        return cast(type[AsyncRemoteWorkflow], partial(AsyncRemoteWorkflow, _client=self))

    @property
    def Function(self) -> type[AsyncNotteFunction]:
        """Create an AsyncNotteFunction factory bound to this client."""
        return cast(type[AsyncNotteFunction], partial(AsyncNotteFunction, _client=self))

    @property
    def AgentFallback(self) -> type[AsyncRemoteAgentFallback]:
        """Create an AsyncRemoteAgentFallback factory bound to this client."""
        return cast(type[AsyncRemoteAgentFallback], partial(AsyncRemoteAgentFallback, _client=self))

    async def health_check(self) -> None:
        """Health check the Notte API."""
        await self.sessions.health_check()

    @overload
    async def scrape(
        self, /, url: str, *, raise_on_failure: bool = True, **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> str: ...

    @overload
    async def scrape(
        self,
        /,
        url: str,
        *,
        instructions: str,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> dict[str, Any]: ...

    @overload
    async def scrape(
        self,
        /,
        url: str,
        *,
        instructions: str,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[BaseModel]: ...

    @overload
    async def scrape(
        self,
        /,
        url: str,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> TBaseModel: ...

    @overload
    async def scrape(
        self,
        /,
        url: str,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    @overload
    async def scrape(
        self, /, url: str, *, only_images: Literal[True], raise_on_failure: bool = True
    ) -> list[ImageData]: ...

    async def scrape(
        self, /, url: str, *, raise_on_failure: bool = True, **data: Unpack[ScrapeRequestDict]
    ) -> StructuredData[BaseModel] | BaseModel | dict[str, Any] | str | list[ImageData]:
        """Scrape a URL using a temporary session.

        Example:
            ```python
            async with AsyncNotteClient() as client:
                markdown = await client.scrape("https://www.google.com")
            ```

        Args:
            url: The URL to scrape.
            raise_on_failure: If True (default), raises ScrapeFailedError when structured data
                extraction fails and returns the extracted data directly.
            **data: Additional parameters for the scrape.

        Returns:
            When using instructions/response_format and raise_on_failure=True: returns the extracted data directly.
            When raise_on_failure=False: returns StructuredData wrapper so user can check .success.
            For markdown scraping: returns str.
            For image scraping: returns list[ImageData].
        """
        async with self.Session(open_viewer=False, perception_type="fast") as session:
            result = await session.execute(GotoAction(url=url))
            if not result.success and result.exception is not None:
                raise result.exception
            return await session.scrape(raise_on_failure=raise_on_failure, **data)
