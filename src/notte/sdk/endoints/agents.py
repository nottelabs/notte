from collections.abc import Sequence
from typing import Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte.agents.falco.types import StepAgentOutput
from notte.sdk.endoints.base import BaseClient, NotteEndpoint
from notte.sdk.types import (
    AgentListRequest,
    AgentResponse,
    AgentRunRequest,
    AgentRunRequestDict,
    ListRequestDict,
)
from notte.sdk.types import (
    AgentStatusResponse as _AgentStatusResponse,
)

AgentStatusResponse = _AgentStatusResponse[StepAgentOutput]


@final
class AgentsClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    AGENT_RUN = "run"
    AGENT_STOP = "{agent_id}/stop"
    AGENT_STATUS = "{agent_id}"
    AGENT_LIST = ""

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
    ):
        super().__init__(base_endpoint_path="agents", api_key=api_key, server_url=server_url)
        self._last_agent_response: AgentResponse | None = None

    @staticmethod
    def agent_run_endpoint() -> NotteEndpoint[AgentResponse]:
        return NotteEndpoint(path=AgentsClient.AGENT_RUN, response=AgentResponse, method="POST")

    @staticmethod
    def agent_stop_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentResponse]:
        path = AgentsClient.AGENT_STOP
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="DELETE")

    @staticmethod
    def agent_status_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentStatusResponse]:
        path = AgentsClient.AGENT_STATUS
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="GET")

    @staticmethod
    def agent_list_endpoint(params: AgentListRequest | None = None) -> NotteEndpoint[AgentResponse]:
        return NotteEndpoint(
            path=AgentsClient.AGENT_LIST,
            response=AgentResponse,
            method="GET",
            request=None,
            params=params,
        )

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        return [
            AgentsClient.agent_run_endpoint(),
            AgentsClient.agent_stop_endpoint(),
            AgentsClient.agent_status_endpoint(),
            AgentsClient.agent_list_endpoint(),
        ]

    @property
    def agent_id(self) -> str | None:
        return self._last_agent_response.agent_id if self._last_agent_response is not None else None

    def get_agent_id(self, agent_id: str | None = None) -> str:
        if agent_id is None:
            if self._last_agent_response is None:
                raise ValueError("No agent to get agent id from")
            agent_id = self._last_agent_response.agent_id
        return agent_id

    def run(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        request = AgentRunRequest.model_validate(data)
        response = self.request(AgentsClient.agent_run_endpoint().with_request(request))
        self._last_agent_response = response
        return response

    def close(self, agent_id: str) -> AgentResponse:
        agent_id = self.get_agent_id(agent_id)
        endpoint = AgentsClient.agent_stop_endpoint(agent_id=agent_id)
        response = AgentResponse.model_validate(self.request(endpoint))
        self._last_agent_response = None
        return response

    def status(self, agent_id: str) -> AgentResponse:
        agent_id = self.get_agent_id(agent_id)
        endpoint = AgentsClient.agent_status_endpoint(agent_id=agent_id)
        response = AgentResponse.model_validate(self.request(endpoint))
        self._last_agent_response = response
        return response

    def list(self, **data: Unpack[ListRequestDict]) -> Sequence[AgentResponse]:
        params = AgentListRequest.model_validate(data)
        endpoint = AgentsClient.agent_list_endpoint(params=params)
        return self.request_list(endpoint)
