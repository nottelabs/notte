# pyright: reportImportCycles=false
from functools import partial
from typing import Literal, Unpack, cast, overload

from notte_core import enable_nest_asyncio
from notte_core.actions import GotoAction
from notte_core.common.config import LlmModel
from notte_core.common.logging import logger
from notte_core.data.space import ImageData, StructuredData, TBaseModel
from pydantic import BaseModel
from typing_extensions import final

from notte_sdk.agent_fallback import RemoteAgentFallback
from notte_sdk.endpoints.agents import AgentsClient, BatchRemoteAgent, RemoteAgent
from notte_sdk.endpoints.files import FileStorageClient, RemoteFileStorage
from notte_sdk.endpoints.functions import NotteFunction
from notte_sdk.endpoints.personas import NottePersona, PersonasClient
from notte_sdk.endpoints.profiles import ProfilesClient
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
        self.profiles: ProfilesClient = ProfilesClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.files: FileStorageClient = FileStorageClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.workflows: WorkflowsClient = WorkflowsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )

        self.functions = self.workflows

        if self.sessions.server_url != self.sessions.DEFAULT_NOTTE_API_URL:
            logger.warning(f"NOTTE_API_URL is set to: {self.sessions.server_url}")

    @property
    def models(self) -> type[LlmModel]:
        return LlmModel

    @property
    def Session(self) -> type[RemoteSession]:
        return cast(type[RemoteSession], partial(RemoteSession, _client=self.sessions, headless=True))

    @property
    def Agent(self) -> type[RemoteAgent]:
        return cast(type[RemoteAgent], partial(RemoteAgent, _client=self.agents))

    @property
    def BatchAgent(self) -> type[BatchRemoteAgent]:
        return cast(type[BatchRemoteAgent], partial(BatchRemoteAgent, _client=self))

    @property
    def Vault(self) -> type[NotteVault]:
        return cast(type[NotteVault], partial(NotteVault, _client=self.vaults))

    @property
    def Persona(self) -> type[NottePersona]:
        return cast(type[NottePersona], partial(NottePersona, _client=self))

    @property
    def FileStorage(self) -> type[RemoteFileStorage]:
        return cast(type[RemoteFileStorage], partial(RemoteFileStorage, _client=self.files))

    @property
    def Workflow(self) -> type[RemoteWorkflow]:
        return cast(type[RemoteWorkflow], partial(RemoteWorkflow, _client=self))

    @property
    def Function(self) -> type[NotteFunction]:
        return cast(type[NotteFunction], partial(NotteFunction, _client=self))

    @property
    def AgentFallback(self) -> type[RemoteAgentFallback]:
        return cast(type[RemoteAgentFallback], partial(RemoteAgentFallback, _client=self))

    def health_check(self) -> None:
        """
        Health check the Notte API.
        """
        return self.sessions.health_check()

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
        with self.Session(open_viewer=False, perception_type="fast") as session:
            result = session.execute(GotoAction(url=url))
            if not result.success and result.exception is not None:
                raise result.exception
            return session.scrape(**data)
