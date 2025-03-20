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
        """
        Initialize an AgentsClient instance.
        
        Sets up the client with a fixed 'agents' endpoint and optional API key and server URL.
        Also initializes the internal tracker for the last agent response.
            
        Args:
            api_key: Optional API key for authentication.
            server_url: Optional URL of the Notte API server.
        """
        super().__init__(base_endpoint_path="agents", api_key=api_key, server_url=server_url)
        self._last_agent_response: AgentResponse | None = None

    @staticmethod
    def agent_run_endpoint() -> NotteEndpoint[AgentResponse]:
        """
        Returns an endpoint for running an agent.
        
        Constructs and returns a NotteEndpoint instance configured for executing an agent run request
        using a POST HTTP method. The endpoint uses the AgentsClient.AGENT_RUN path and expects a response
        conforming to the AgentResponse model.
        """
        return NotteEndpoint(path=AgentsClient.AGENT_RUN, response=AgentResponse, method="POST")

    @staticmethod
    def agent_stop_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentResponse]:
        """
        Generates an endpoint for stopping an agent.
        
        If an agent ID is provided, the stop path is formatted with that ID.
        Otherwise, the default stop path is used.
        
        Args:
            agent_id: Optional identifier for the agent to stop.
        
        Returns:
            A NotteEndpoint configured with the DELETE method for stopping an agent.
        """
        path = AgentsClient.AGENT_STOP
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="DELETE")

    @staticmethod
    def agent_status_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentStatusResponse]:
        """
        Constructs a NotteEndpoint to retrieve an agent's status.
        
        If an agent ID is provided, the endpoint path is formatted with that ID; otherwise, the default agent status path is used.
        
        Args:
            agent_id: Optional; the identifier of the agent whose status is requested.
        
        Returns:
            A NotteEndpoint configured with the GET method and expecting an AgentStatusResponse.
        """
        path = AgentsClient.AGENT_STATUS
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="GET")

    @staticmethod
    def agent_list_endpoint(params: AgentListRequest | None = None) -> NotteEndpoint[AgentResponse]:
        """
        Creates a NotteEndpoint for listing agents.
        
        Configures the endpoint for a GET request to retrieve agents, optionally including
        query parameters from the provided AgentListRequest.
        
        Args:
            params: Optional AgentListRequest containing query parameters for filtering the list.
        
        Returns:
            NotteEndpoint[AgentResponse]: An endpoint instance configured for listing agents.
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
        Return a sequence of API endpoints for agent management.
        
        Returns:
            Sequence[NotteEndpoint[BaseModel]]: Endpoints for running, stopping, 
            checking the status, and listing agents.
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
        Retrieves the agent ID from the last agent response.
        
        Returns:
            The agent ID if a recent agent response is available; otherwise, None.
        """
        return self._last_agent_response.agent_id if self._last_agent_response is not None else None

    def get_agent_id(self, agent_id: str | None = None) -> str:
        """
        Retrieves the agent identifier from the provided argument or the last response.
        
        If an agent ID is supplied, it is returned immediately. Otherwise, the method attempts
        to extract the agent ID from the most recent agent response. A ValueError is raised if 
        no agent ID is available.
            
        Args:
            agent_id (str | None): Optional agent identifier. If omitted, the agent ID from the
                last received response is used.
        
        Returns:
            str: The agent identifier.
        
        Raises:
            ValueError: If no agent ID is provided and there is no previous agent response.
        """
        if agent_id is None:
            if self._last_agent_response is None:
                raise ValueError("No agent to get agent id from")
            agent_id = self._last_agent_response.agent_id
        return agent_id

    def run(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        """
        Submits an agent run request.
        
        Validates the provided keyword arguments against the AgentRunRequest model,
        sends the request using the agent run endpoint, updates the client's last agent
        response, and returns the API response.
        
        Args:
            **data: Arbitrary keyword arguments specifying the parameters for running an agent.
        
        Returns:
            AgentResponse: The response from the agent run request.
        """
        request = AgentRunRequest.model_validate(data)
        response = self.request(AgentsClient.agent_run_endpoint().with_request(request))
        self._last_agent_response = response
        return response

    def close(self, agent_id: str) -> AgentResponse:
        """
        Stops the agent with the specified identifier.
        
        Retrieves the effective agent identifier using get_agent_id, sends a stop request
        to the agent stop endpoint, validates the response as an AgentResponse, and resets
        the client's last stored agent response.
        
        Parameters:
            agent_id (str): The unique identifier of the agent to stop.
        
        Returns:
            AgentResponse: The response after stopping the agent.
        
        Raises:
            ValueError: If no valid agent identifier is available.
        """
        agent_id = self.get_agent_id(agent_id)
        endpoint = AgentsClient.agent_stop_endpoint(agent_id=agent_id)
        response = AgentResponse.model_validate(self.request(endpoint))
        self._last_agent_response = None
        return response

    def status(self, agent_id: str) -> AgentResponse:
        """
        Retrieves the current status of an agent.
        
        Validates the given agent identifier (or falls back to the last recorded ID) and sends a
        request to the status endpoint. The response is then validated, stored as the last agent
        response, and returned.
        
        Args:
            agent_id: The unique identifier of the agent.
        
        Returns:
            AgentResponse: The validated response containing the agent's current status.
        
        Raises:
            ValueError: If a valid agent identifier cannot be determined.
        """
        agent_id = self.get_agent_id(agent_id)
        endpoint = AgentsClient.agent_status_endpoint(agent_id=agent_id)
        response = AgentResponse.model_validate(self.request(endpoint))
        self._last_agent_response = response
        return response

    def list(self, **data: Unpack[ListRequestDict]) -> Sequence[AgentResponse]:
        """
        Retrieve a list of agents.
        
        Validates the provided listing parameters against the AgentListRequest schema,
        constructs the corresponding endpoint, and returns a sequence of AgentResponse
        objects with the agent details.
        
        Args:
            **data: Arbitrary keyword arguments compliant with the AgentListRequest
                    schema, used to filter and paginate the agent listing.
        
        Returns:
            Sequence[AgentResponse]: A list of agents retrieved from the API.
        """
        params = AgentListRequest.model_validate(data)
        endpoint = AgentsClient.agent_list_endpoint(params=params)
        return self.request_list(endpoint)
