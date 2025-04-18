from typing_extensions import final

from notte_sdk.endpoints.agents import AgentsClient
from notte_sdk.endpoints.env import EnvClient
from notte_sdk.endpoints.persona import PersonaClient
from notte_sdk.endpoints.sessions import SessionsClient
from notte_sdk.endpoints.vault import VaultClient


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
        of SessionsClient, AgentsClient, and EnvClient.

        Args:
            api_key: Optional API key for authentication.
        """
        self.sessions: SessionsClient = SessionsClient(api_key=api_key, verbose=verbose)
        self.agents: AgentsClient = AgentsClient(api_key=api_key, verbose=verbose)
        self.env: EnvClient = EnvClient(api_key=api_key, verbose=verbose)
        self.persona: PersonaClient = PersonaClient(api_key=api_key, verbose=verbose)
        self.vault: VaultClient = VaultClient(api_key=api_key, persona_client=self.persona, verbose=verbose)
