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
        self.sessions: SessionsClient = SessionsClient(api_key=api_key, server_url=server_url)
        self.agents: AgentsClient = AgentsClient(api_key=api_key, server_url=server_url)
        self.env: EnvClient = EnvClient(api_key=api_key, server_url=server_url)

    def local(self) -> Self:
        _ = self.sessions.local()
        _ = self.agents.local()
        _ = self.env.local()
        return self

    def remote(self) -> Self:
        _ = self.sessions.remote()
        _ = self.agents.remote()
        _ = self.env.remote()
        return self
