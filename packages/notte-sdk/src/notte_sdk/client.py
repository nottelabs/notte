# pyright: reportImportCycles=false
from functools import partial
from typing import Literal, Unpack, overload

import notte_core.actions as actions
from loguru import logger
from notte_core import enable_nest_asyncio
from notte_core.actions import GotoAction
from notte_core.common.config import LlmModel
from notte_core.data.space import ImageData, StructuredData, TBaseModel
from pydantic import BaseModel
from typing_extensions import final

from notte_sdk.agent_fallback import RemoteAgentFallback
from notte_sdk.endpoints.agents import AgentsClient, BatchRemoteAgent, RemoteAgent
from notte_sdk.endpoints.files import FileStorageClient, RemoteFileStorage
from notte_sdk.endpoints.personas import NottePersona, PersonasClient
from notte_sdk.endpoints.sessions import RemoteSession, SessionsClient, SessionViewerType
from notte_sdk.endpoints.vaults import NotteVault, VaultsClient
from notte_sdk.endpoints.workflows import RemoteWorkflow, WorkflowsClient
from notte_sdk.types import ScrapeMarkdownParamsDict, ScrapeRequestDict

enable_nest_asyncio()


@final
class NotteClient:
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
        viewer_type: SessionViewerType = SessionViewerType.BROWSER,
    ):
        """Initialize a NotteClient instance.

        Initializes the NotteClient with the specified API key and server URL, creating instances
        of SessionsClient, AgentsClient, VaultsClient, and PersonasClient.

        Args:
            api_key: Optional API key for authentication.
        """

        self.sessions: SessionsClient = SessionsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose, viewer_type=viewer_type
        )
        self.agents: AgentsClient = AgentsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.personas: PersonasClient = PersonasClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.vaults: VaultsClient = VaultsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.files: FileStorageClient = FileStorageClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.workflows: WorkflowsClient = WorkflowsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )

        if self.sessions.server_url != self.sessions.DEFAULT_NOTTE_API_URL:
            logger.warning(f"NOTTE_API_URL is set to: {self.sessions.server_url}")

    @property
    def models(self) -> type[LlmModel]:
        """
        Return the LlmModel class.
        """
        return LlmModel

    @property
    def actions(self):
        """
        Return the actions module.
        """
        return actions

    def health_check(self) -> None:
        """
        Health check the Notte API.
        """
        return self.sessions.health_check()

    @property
    def Agent(self):
        return partial(RemoteAgent, _client=self.agents)

    @property
    def BatchAgent(self):
        return partial(BatchRemoteAgent, _client=self)

    @property
    def Session(self):
        return partial(RemoteSession, _client=self.sessions)

    @property
    def Vault(self):
        return partial(NotteVault, _client=self.vaults)

    @property
    def Persona(self):
        return partial(NottePersona, _client=self)

    @property
    def FileStorage(self):
        return partial(RemoteFileStorage, _client=self.files)

    @property
    def Workflow(self):
        return partial(RemoteWorkflow, _client=self)

    @property
    def AgentFallback(self):
        return partial(RemoteAgentFallback, _client=self)

    @overload
    def scrape(self, /, url: str, **params: Unpack[ScrapeMarkdownParamsDict]) -> str: ...

    @overload
    def scrape(  # pyright: ignore [reportOverlappingOverload]
        self,
        /,
        url: str,
        *,
        instructions: str,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[BaseModel]: ...

    @overload
    def scrape(  # pyright: ignore [reportOverlappingOverload]
        self,
        /,
        url: str,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    @overload
    def scrape(self, /, url: str, *, only_images: Literal[True]) -> list[ImageData]: ...  # pyright: ignore [reportOverlappingOverload]

    def scrape(
        self, /, url: str, **data: Unpack[ScrapeRequestDict]
    ) -> str | StructuredData[BaseModel] | list[ImageData]:
        """
        Scrape the current page data.

        This endpoint is a wrapper around the `session.scrape` method that automatically starts a new session, goes to the given URL, and scrapes the page.

        **Example:**
        ```python
        from notte_sdk import NotteClient

        client = NotteClient()
        markdown = client.scrape("https://www.google.com", only_main_content=False)
        ```

        With structured data:
        ```python
        from notte_sdk import NotteClient
        from pydantic import BaseModel

        # Define your Pydantic model
        ...

        client = NotteClient()
        data = client.scrape(
            "https://www.notte.cc",
            response_format=Product,
            instructions="Extract the products names and prices"
        )
        ```

        Args:
            url: The URL to scrape.
            **data: Additional parameters for the scrape.

        Returns:
            The scraped data.
        """
        with self.Session(headless=True, perception_type="fast") as session:
            result = session.execute(GotoAction(url=url))
            if not result.success and result.exception is not None:
                raise result.exception
            return session.scrape(**data)
