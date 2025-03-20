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
        """Initialize a NotteClient instance.
        
        Initializes the NotteClient with the specified API key and server URL, creating instances
        of SessionsClient, AgentsClient, and EnvClient.
         
        Args:
            api_key: Optional API key for authentication.
            server_url: Optional URL for connecting to the Notte API.
        """
        self.sessions: SessionsClient = SessionsClient(api_key=api_key, server_url=server_url)
        self.agents: AgentsClient = AgentsClient(api_key=api_key, server_url=server_url)
        self.env: EnvClient = EnvClient(api_key=api_key, server_url=server_url)

    def local(self) -> Self:
        """
        Switches the NotteClient and its sub-clients to local mode.
        
        Calls the local() method on the sessions, agents, and env clients to configure them for local operations, and returns the updated NotteClient instance.
        """
        _ = self.sessions.local()
        _ = self.agents.local()
        _ = self.env.local()
        return self

    def remote(self) -> Self:
        """
        Switches the client to remote mode.
        
        Invokes the remote() method on the sessions, agents, and environment clients to configure
        them for remote operations, and returns the current instance to enable method chaining.
        """
        _ = self.sessions.remote()
        _ = self.agents.remote()
        _ = self.env.remote()
        return self
