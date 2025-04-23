from typing import Unpack

from notte_core.data.space import DataSpace
from typing_extensions import final

from notte_sdk.endpoints.agents import AgentsClient, RemoteAgentFactory
from notte_sdk.endpoints.personas import PersonasClient
from notte_sdk.endpoints.sessions import RemoteSessionFactory, SessionsClient
from notte_sdk.endpoints.vaults import VaultsClient
from notte_sdk.types import ScrapeRequestDict


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
        verbose: bool = False,
    ):
        """Initialize a NotteClient instance.

        Initializes the NotteClient with the specified API key and server URL, creating instances
        of SessionsClient, AgentsClient, VaultsClient, and PersonasClient.

        Args:
            api_key: Optional API key for authentication.
        """
        self.sessions: SessionsClient = SessionsClient(api_key=api_key, verbose=verbose)
        self.agents: AgentsClient = AgentsClient(api_key=api_key, verbose=verbose)
        self.personas: PersonasClient = PersonasClient(api_key=api_key, verbose=verbose)
        self.vaults: VaultsClient = VaultsClient(api_key=api_key, persona_client=self.personas, verbose=verbose)

    @property
    def Agent(self) -> RemoteAgentFactory:
        return RemoteAgentFactory(self.agents)

    @property
    def Session(self) -> RemoteSessionFactory:
        return RemoteSessionFactory(self.sessions)

    def scrape(self, **data: Unpack[ScrapeRequestDict]) -> DataSpace:
        with self.Session() as session:
            return session.scrape(**data)
