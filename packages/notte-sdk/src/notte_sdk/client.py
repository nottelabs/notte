from typing import Unpack

from loguru import logger
from notte_core import enable_nest_asyncio
from notte_core.actions import ActionValidation
from notte_core.data.space import DataSpace
from typing_extensions import final

from notte_sdk.endpoints.agents import AgentsClient, RemoteAgentFactory
from notte_sdk.endpoints.personas import PersonasClient
from notte_sdk.endpoints.sessions import RemoteSessionFactory, SessionsClient, SessionViewerType
from notte_sdk.endpoints.vaults import VaultsClient
from notte_sdk.types import AgentResponse, ScrapeRequestDict

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
            api_key=api_key, server_url=server_url, verbose=verbose, viewer_type=viewer_type
        )
        self.agents: AgentsClient = AgentsClient(api_key=api_key, server_url=server_url, verbose=verbose)
        self.personas: PersonasClient = PersonasClient(api_key=api_key, server_url=server_url, verbose=verbose)
        self.vaults: VaultsClient = VaultsClient(api_key=api_key, server_url=server_url, verbose=verbose)
        if self.sessions.server_url != self.sessions.DEFAULT_NOTTE_API_URL:
            logger.warning(f"NOTTE_API_URL is set to: {self.sessions.server_url}")

    @property
    def Agent(self) -> RemoteAgentFactory:
        return RemoteAgentFactory(self.agents, open_viewer=self.sessions.viewer)

    @property
    def Session(self) -> RemoteSessionFactory:
        return RemoteSessionFactory(self.sessions)

    def scrape(self, **data: Unpack[ScrapeRequestDict]) -> DataSpace:
        with self.Session() as session:
            return session.scrape(**data)

    def repeat(self, session_id: str, agent_id: str) -> AgentResponse:
        """
        Repeat the agent_id action in sequence
        """
        # Step 1: get the agent status
        agent_status = self.agents._status(agent_id=agent_id)  # pyright: ignore[reportPrivateUsage]
        # Replay each step
        for step in agent_status.steps:
            try:
                action = ActionValidation.model_validate(step).action
            except Exception as e:
                raise ValueError(
                    f"Agent {agent_id} contains invalid action: {step}. Please record a new agent with the same task."
                ) from e
            _ = self.sessions.page.step(session_id=session_id, action=action)
        return self.agents._status(agent_id=agent_id)  # pyright: ignore[reportPrivateUsage]
