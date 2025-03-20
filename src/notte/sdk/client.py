from typing import Self

from typing_extensions import final

from notte.sdk.endoints.agents import AgentsClient
from notte.sdk.endoints.env import EnvClient
from notte.sdk.endoints.sessions import SessionsClient


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
    ):
        """
        Initialize a NotteClient instance.
        
        This method creates underlying clients for managing sessions, agents,
        and environment configurations using the provided API key and server URL.
        
        Args:
            api_key: Optional API key for authentication.
            server_url: Optional base URL of the Notte API server.
        """
        self.sessions: SessionsClient = SessionsClient(api_key=api_key, server_url=server_url)
        self.agents: AgentsClient = AgentsClient(api_key=api_key, server_url=server_url)
        self.env: EnvClient = EnvClient(api_key=api_key, server_url=server_url)

    def local(self) -> Self:
        """
        Switches all client instances to local mode.
        
        Calls the local() method on the sessions, agents, and env clients to enable local operations and returns the NotteClient instance for method chaining.
        """
        _ = self.sessions.local()
        _ = self.agents.local()
        _ = self.env.local()
        return self

    def remote(self) -> Self:
        """
        Switches the client to remote mode.
        
        Invokes the remote() method on the SessionsClient, AgentsClient, and EnvClient
        instances to configure them for remote API interactions, and returns the
        client instance.
        """
        _ = self.sessions.remote()
        _ = self.agents.remote()
        _ = self.env.remote()
        return self
