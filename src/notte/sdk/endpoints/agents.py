from collections.abc import Sequence
from typing import Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte.agents.falco.types import StepAgentOutput
from notte.sdk.endpoints.base import BaseClient, NotteEndpoint
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
    ):
        """
        Initialize an AgentsClient instance.

        Configures the client to use the "agents" endpoint path and sets optional API key and server URL for authentication and server configuration. The initial state has no recorded agent response.

        Args:
            api_key: Optional API key for authenticating requests.
        """
        super().__init__(base_endpoint_path="agents", api_key=api_key)
        self._last_agent_response: AgentResponse | None = None

    @staticmethod
    def agent_run_endpoint() -> NotteEndpoint[AgentResponse]:
        """
        Returns an endpoint for running an agent.

        Creates a NotteEndpoint configured with the AGENT_RUN path, a POST method, and an expected AgentResponse.
        """
        return NotteEndpoint(path=AgentsClient.AGENT_RUN, response=AgentResponse, method="POST")

    @staticmethod
    def agent_stop_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentResponse]:
        """
        Constructs a DELETE endpoint for stopping an agent.

        If an agent ID is provided, it is inserted into the endpoint URL. The returned
        endpoint is configured with the DELETE HTTP method and expects an AgentStatusResponse.

        Args:
            agent_id (str, optional): The identifier of the agent to stop. If omitted,
                the URL template will remain unformatted.

        Returns:
            NotteEndpoint[AgentResponse]: The endpoint object for stopping the agent.
        """
        path = AgentsClient.AGENT_STOP
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="DELETE")

    @staticmethod
    def agent_status_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentStatusResponse]:
        """
        Creates an endpoint for retrieving an agent's status.

        If an agent ID is provided, formats the endpoint path to target that specific agent.

        Args:
            agent_id: Optional identifier of the agent; if specified, the endpoint path will include this ID.

        Returns:
            NotteEndpoint configured with the GET method and AgentStatusResponse as the expected response.
        """
        path = AgentsClient.AGENT_STATUS
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="GET")

    @staticmethod
    def agent_list_endpoint(params: AgentListRequest | None = None) -> NotteEndpoint[AgentResponse]:
        """
        Creates a NotteEndpoint for listing agents.

        Returns an endpoint configured with the agent listing path and a GET method.
        The optional params argument provides filtering or pagination details for the request.
        """
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
        """
        Returns a list of endpoints for agent operations.

        Aggregates endpoints for running, stopping, checking status, and listing agents.
        """
        return [
            AgentsClient.agent_run_endpoint(),
            AgentsClient.agent_stop_endpoint(),
            AgentsClient.agent_status_endpoint(),
            AgentsClient.agent_list_endpoint(),
        ]

    @property
    def agent_id(self) -> str | None:
        """
        Returns the agent ID from the last agent response, or None if no response exists.

        This property retrieves the identifier from the most recent agent operation response.
        If no agent has been run or if the response is missing, it returns None.
        """
        return self._last_agent_response.agent_id if self._last_agent_response is not None else None

    def get_agent_id(self, agent_id: str | None = None) -> str:
        """
        Retrieves the agent ID to be used for agent operations.

        If an `agent_id` is provided, it is returned directly. Otherwise, the method attempts to obtain the agent ID from the client's last agent response. Raises a ValueError if no agent ID is available.

        Args:
            agent_id (Optional[str]): An agent identifier. If omitted, the ID from the last agent response is used.

        Raises:
            ValueError: If no agent ID is provided and the client has no recorded agent response.

        Returns:
            str: The determined agent identifier.
        """
        if agent_id is None:
            if self._last_agent_response is None:
                raise ValueError("No agent to get agent id from")
            agent_id = self._last_agent_response.agent_id
        return agent_id

    def run(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        """
        Run an agent with the specified request parameters.

        Validates the provided data using the AgentRunRequest model, sends a run request through the
        designated endpoint, updates the last agent response, and returns the resulting AgentResponse.

        Args:
            **data: Keyword arguments representing the fields of an AgentRunRequest.

        Returns:
            AgentResponse: The response obtained from the agent run request.
        """
        request = AgentRunRequest.model_validate(data)
        response = self.request(AgentsClient.agent_run_endpoint().with_request(request))
        self._last_agent_response = response
        return response

    def close(self, agent_id: str) -> AgentResponse:
        """
        Stops the specified agent and clears the last agent response.

        Retrieves a valid agent identifier using the provided value or the last stored
        response, sends a stop request to the API, resets the internal agent response,
        and returns the resulting AgentResponse.

        Args:
            agent_id: The identifier of the agent to stop.

        Returns:
            AgentResponse: The response from the stop operation.

        Raises:
            ValueError: If a valid agent identifier cannot be determined.
        """
        agent_id = self.get_agent_id(agent_id)
        endpoint = AgentsClient.agent_stop_endpoint(agent_id=agent_id)
        response = self.request(endpoint)
        self._last_agent_response = None
        return response

    def status(self, agent_id: str) -> AgentStatusResponse:
        """
        Retrieves the status of the specified agent.

        Queries the API for the current status of an agent using a validated agent ID.
        The provided ID is confirmed (or obtained from the last response if needed), and the
        resulting status is stored internally before being returned.

        Args:
            agent_id: Unique identifier of the agent to check.

        Returns:
            AgentResponse: The current status information of the specified agent.

        Raises:
            ValueError: If no valid agent ID can be determined.
        """
        agent_id = self.get_agent_id(agent_id)
        endpoint = AgentsClient.agent_status_endpoint(agent_id=agent_id)
        response = self.request(endpoint)
        self._last_agent_response = response
        return response

    def list(self, **data: Unpack[ListRequestDict]) -> Sequence[AgentResponse]:
        """
        Lists agents matching specified criteria.

        Validates the keyword arguments using the AgentListRequest model, constructs
        the corresponding endpoint for listing agents, and returns a sequence of agent
        responses.

        Args:
            data: Arbitrary keyword arguments representing filter criteria for agents.

        Returns:
            A sequence of AgentResponse objects.
        """
        params = AgentListRequest.model_validate(data)
        endpoint = AgentsClient.agent_list_endpoint(params=params)
        return self.request_list(endpoint)
