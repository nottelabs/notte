"""Async client for the Notte SDK."""
# Auto-generated from _async/ - DO NOT EDIT DIRECTLY

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

from notte_sdk._sync.agent_fallback import RemoteAgentFallback
from notte_sdk._sync.agents import AgentsClient, BatchRemoteAgent, RemoteAgent
from notte_sdk._sync.files import FileStorageClient, RemoteFileStorage
from notte_sdk._sync.http import HTTPClient
from notte_sdk._sync.personas import NottePersona, PersonasClient
from notte_sdk._sync.profiles import ProfilesClient
from notte_sdk._sync.sessions import (
    RemoteSession,
    SessionsClient,
    SessionViewerType,
)
from notte_sdk._sync.vaults import NotteVault, VaultsClient
from notte_sdk._sync.workflows import NotteFunction, RemoteWorkflow, WorkflowsClient
from notte_sdk.errors import AuthenticationError
from notte_sdk.types import ScrapeMarkdownParamsDict, ScrapeRequestDict


@final
class NotteClient:
    """Async client for the Notte API.

    Example:
        ```python
        with NotteClient() as client:
            with client.Session() as session:
                session.execute(type="goto", url="https://www.notte.cc")
                markdown = session.scrape()
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
        """Initialize an NotteClient instance.

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
        self._http = HTTPClient(
            token=self._api_key,
            base_url=self._server_url,
        )

        # Initialize endpoint clients
        self.sessions: SessionsClient = SessionsClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
            viewer_type=viewer_type,
        )
        self.agents: AgentsClient = AgentsClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.personas: PersonasClient = PersonasClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.vaults: VaultsClient = VaultsClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.profiles: ProfilesClient = ProfilesClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.files: FileStorageClient = FileStorageClient(
            root_client=self,
            http_client=self._http,
            server_url=self._server_url,
            api_key=self._api_key,
            verbose=verbose,
        )
        self.workflows: WorkflowsClient = WorkflowsClient(
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

    def __enter__(self) -> "NotteClient":
        """Async context manager entry."""
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit - close the HTTP client."""
        self._http.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()

    @property
    def models(self) -> type[LlmModel]:
        return LlmModel

    @property
    def Session(self) -> type[RemoteSession]:
        """Create an RemoteSession factory bound to this client."""
        return cast(type[RemoteSession], partial(RemoteSession, _client=self.sessions))

    @property
    def Vault(self) -> type[NotteVault]:
        """Create an NotteVault factory bound to this client."""
        return cast(type[NotteVault], partial(NotteVault, _client=self.vaults))

    @property
    def Persona(self) -> type[NottePersona]:
        """Create an NottePersona factory bound to this client."""
        return cast(type[NottePersona], partial(NottePersona, _client=self))

    @property
    def FileStorage(self) -> type[RemoteFileStorage]:
        """Create an RemoteFileStorage factory bound to this client."""
        return cast(type[RemoteFileStorage], partial(RemoteFileStorage, _client=self.files))

    @property
    def Agent(self) -> type[RemoteAgent]:
        """Create an RemoteAgent factory bound to this client."""
        return cast(type[RemoteAgent], partial(RemoteAgent, _client=self.agents))

    @property
    def BatchAgent(self) -> type[BatchRemoteAgent]:
        """Create an BatchRemoteAgent factory bound to this client."""
        return cast(type[BatchRemoteAgent], partial(BatchRemoteAgent, _client=self))

    @property
    def Workflow(self) -> type[RemoteWorkflow]:
        """Create an RemoteWorkflow factory bound to this client."""
        return cast(type[RemoteWorkflow], partial(RemoteWorkflow, _client=self))

    @property
    def Function(self) -> type[NotteFunction]:
        """Create an NotteFunction factory bound to this client."""
        return cast(type[NotteFunction], partial(NotteFunction, _client=self))

    @property
    def AgentFallback(self) -> type[RemoteAgentFallback]:
        """Create an RemoteAgentFallback factory bound to this client."""
        return cast(type[RemoteAgentFallback], partial(RemoteAgentFallback, _client=self))

    def health_check(self) -> None:
        """Health check the Notte API."""
        self.sessions.health_check()

    @overload
    def scrape(
        self, /, url: str, *, raise_on_failure: bool = True, **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> str: ...

    @overload
    def scrape(
        self,
        /,
        url: str,
        *,
        instructions: str,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> dict[str, Any]: ...

    @overload
    def scrape(
        self,
        /,
        url: str,
        *,
        instructions: str,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[BaseModel]: ...

    @overload
    def scrape(
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
    def scrape(
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
    def scrape(self, /, url: str, *, only_images: Literal[True], raise_on_failure: bool = True) -> list[ImageData]: ...

    def scrape(
        self, /, url: str, *, raise_on_failure: bool = True, **data: Unpack[ScrapeRequestDict]
    ) -> StructuredData[BaseModel] | BaseModel | dict[str, Any] | str | list[ImageData]:
        """Scrape a URL using a temporary session.

        Example:
            ```python
            with NotteClient() as client:
                markdown = client.scrape("https://www.google.com")
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
        with self.Session(open_viewer=False, perception_type="fast") as session:
            result = session.execute(GotoAction(url=url))
            if not result.success and result.exception is not None:
                raise result.exception
            return session.scrape(raise_on_failure=raise_on_failure, **data)
