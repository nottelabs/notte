import asyncio
import time
from collections.abc import Sequence
from typing import Any, Callable, Unpack

import websockets
from halo import Halo  # pyright: ignore[reportMissingTypeStubs]
from loguru import logger
from notte_core.actions import CompletionAction
from notte_core.common.notifier import BaseNotifier
from notte_core.utils.webp_replay import WebpReplay
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.endpoints.vaults import NotteVault
from notte_sdk.types import (
    DEFAULT_MAX_NB_STEPS,
    AgentCreateRequest,
    AgentCreateRequestDict,
    AgentListRequest,
    AgentListRequestDict,
    AgentResponse,
    AgentRunRequestDict,
    AgentStartRequest,
    AgentStartRequestDict,
    AgentStatus,
    AgentStatusRequest,
    render_agent_status,
)
from notte_sdk.types import AgentStatusResponse as _AgentStatusResponse


# proxy for: StepAgentOutput
class AgentStepResponse(BaseModel):
    state: dict[str, Any]
    actions: list[dict[str, Any]]

    def pretty_string(self, colors: bool = True) -> list[tuple[str, dict[str, str]]]:
        action_str = ""
        actions = self.actions
        for action in actions:
            action_str += f"   ▶ {action}"
        return render_agent_status(
            status=self.state.get("previous_goal_status", "no agent status"),
            summary=self.state.get("page_summary", "no page summary"),
            goal_eval=self.state.get("previous_goal_eval", "no goal eval"),
            next_goal=self.state.get("next_goal", "no next goal"),
            memory=self.state.get("memory", "no memory"),
            action_str=action_str,
            colors=colors,
        )

    def log_pretty_string(self, colors: bool = True) -> None:
        for text, data in self.pretty_string(colors=colors):
            time.sleep(0.1)
            logger.opt(colors=True).info(text, **data)

    def is_done(self) -> bool:
        # check for completion action
        for action in self.actions:
            if action.get("type") == CompletionAction.name():
                return True
        return False


AgentStatusResponse = _AgentStatusResponse[AgentStepResponse]


@final
class AgentsClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    AGENT_START = "start"
    AGENT_START_CUSTOM = "start/custom"
    AGENT_STOP = "{agent_id}/stop"
    AGENT_STATUS = "{agent_id}"
    AGENT_LIST = ""
    # The following endpoints downloads a .webp file
    AGENT_REPLAY = "{agent_id}/replay"
    AGENT_LOGS_WS = "{agent_id}/debug/logs?token={token}"

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize an AgentsClient instance.

        Configures the client to use the "agents" endpoint path and sets optional API key and server URL for authentication and server configuration. The initial state has no recorded agent response.

        Args:
            api_key: Optional API key for authenticating requests.
        """
        super().__init__(base_endpoint_path="agents", server_url=server_url, api_key=api_key, verbose=verbose)

    @staticmethod
    def _agent_start_endpoint() -> NotteEndpoint[AgentResponse]:
        """
        Returns an endpoint for running an agent.

        Creates a NotteEndpoint configured with the AGENT_START path, a POST method, and an expected AgentResponse.
        """
        return NotteEndpoint(path=AgentsClient.AGENT_START, response=AgentResponse, method="POST")

    @staticmethod
    def _agent_start_custom_endpoint() -> NotteEndpoint[AgentResponse]:
        """
        Returns an endpoint for running an agent.
        """
        return NotteEndpoint(path=AgentsClient.AGENT_START_CUSTOM, response=AgentResponse, method="POST")

    @staticmethod
    def _agent_stop_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentResponse]:
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
    def _agent_status_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentStatusResponse]:
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
    def _agent_replay_endpoint(agent_id: str | None = None) -> NotteEndpoint[BaseModel]:
        """
        Creates an endpoint for downloading an agent's replay.
        """
        path = AgentsClient.AGENT_REPLAY
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=BaseModel, method="GET")

    @staticmethod
    def _agent_list_endpoint(params: AgentListRequest | None = None) -> NotteEndpoint[AgentResponse]:
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
            AgentsClient._agent_start_endpoint(),
            AgentsClient._agent_stop_endpoint(),
            AgentsClient._agent_status_endpoint(),
            AgentsClient._agent_list_endpoint(),
            AgentsClient._agent_replay_endpoint(),
        ]

    def _start(self, **data: Unpack[AgentStartRequestDict]) -> AgentResponse:
        """
        Start an agent with the specified request parameters.

        Validates the provided data using the AgentRunRequest model, sends a run request through the
        designated endpoint, updates the last agent response, and returns the resulting AgentResponse.

        Args:
            **data: Keyword arguments representing the fields of an AgentRunRequest.

        Returns:
            AgentResponse: The response obtained from the agent run request.
        """
        request = AgentStartRequest.model_validate(data)
        response = self.request(AgentsClient._agent_start_endpoint().with_request(request))
        return response

    def start_custom(self, request: BaseModel) -> AgentResponse:
        """
        Start an agent with the specified request parameters.
        """
        response = self.request(AgentsClient._agent_start_custom_endpoint().with_request(request))
        return response

    def _wait(
        self,
        agent_id: str,
        polling_interval_seconds: int = 10,
        max_attempts: int = 30,
    ) -> AgentStatusResponse:
        """
        Waits for the specified agent to complete.

        Args:
            agent_id: The identifier of the agent to wait for.
            polling_interval_seconds: The interval between status checks.
            max_attempts: The maximum number of attempts to check the agent's status.

        Returns:
            AgentStatusResponse: The response from the agent status check.
        """
        last_step = 0
        for _ in range(max_attempts):
            response = self._status(agent_id=agent_id)
            if len(response.steps) > last_step:
                for step in response.steps[last_step:]:
                    step.log_pretty_string()
                    if step.is_done():
                        return response

                last_step = len(response.steps)

            if response.status == AgentStatus.closed:
                return response

            spinner = None
            try:
                if not WebpReplay.in_notebook():
                    spinner = Halo(
                        text=f"Waiting {polling_interval_seconds} seconds for agent to complete (current step: {last_step})...",
                    )
                time.sleep(polling_interval_seconds)

            finally:
                if spinner is not None:
                    _ = spinner.succeed()  #  pyright: ignore[reportUnknownMemberType]

        raise TimeoutError("Agent did not complete in time")

    async def watch_logs(self, agent_id: str, max_steps: int) -> None:
        """
        Watch the logs of the specified agent.
        """
        endpoint = NotteEndpoint(path=AgentsClient.AGENT_LOGS_WS, response=BaseModel, method="GET")
        wss_url = self.request_path(endpoint).format(agent_id=agent_id, token=self.token)
        wss_url = wss_url.replace("https://", "wss://").replace("http://", "ws://")

        async def get_messages():
            counter = 0
            async with websockets.client.connect(
                uri=wss_url,
                ping_interval=5,
                ping_timeout=40,
                close_timeout=5,
            ) as websocket:
                try:
                    async for message in websocket:
                        assert isinstance(message, str), f"Expected str, got {type(message)}"
                        response = AgentStepResponse.model_validate_json(message)
                        response.log_pretty_string()
                        counter += 1

                        if response.is_done():
                            logger.info(f"Agent {agent_id} completed in {counter} steps")
                            break

                        if counter >= max_steps:
                            logger.info(f"Agent reached max steps: {max_steps}")
                            break
                except ConnectionError as e:
                    logger.error(f"Connection error: {e}")
                    return
                except Exception as e:
                    logger.error(f"Error: {e}")
                    return

        _ = await get_messages()

    async def watch_logs_and_wait(self, agent_id: str, max_steps: int) -> AgentStatusResponse:
        """
        Asynchronously execute a task with the agent.

        This is currently a wrapper around the synchronous run method.
        In future versions, this might be implemented as a true async operation.

        Args:
            task (str): The task description for the agent to execute.
            url (str | None): Optional starting URL for the task.

        Returns:
            AgentResponse: The response from the completed agent execution.
        """
        _ = await self.watch_logs(agent_id=agent_id, max_steps=max_steps)
        # Wait max 9 seconds for the agent to complete
        TOTAL_WAIT_TIME, ITERATIONS = 9, 3
        for _ in range(ITERATIONS):
            time.sleep(TOTAL_WAIT_TIME / ITERATIONS)
            status = self._status(agent_id=agent_id)
            if status.status == AgentStatus.closed:
                return status
        time.sleep(TOTAL_WAIT_TIME)
        logger.error(f"[Agent] {agent_id} failed to complete in time. Try runnig `agent.status()` after a few seconds.")
        return self._status(agent_id=agent_id)

    def _stop(self, agent_id: str) -> AgentResponse:
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
        endpoint = AgentsClient._agent_stop_endpoint(agent_id=agent_id)
        response = self.request(endpoint)
        return response

    def _run(self, **data: Unpack[AgentStartRequestDict]) -> AgentStatusResponse:  # pyright: ignore [reportUnusedFunction]
        """
        Run an agent with the specified request parameters.
        and wait for completion

        Validates the provided data using the AgentCreateRequest model, sends a run request through the
        designated endpoint, updates the last agent response, and returns the resulting AgentResponse.
        """
        return asyncio.run(self.arun(**data))

    async def arun(self, **data: Unpack[AgentStartRequestDict]) -> AgentStatusResponse:
        """
        Run an async agent with the specified request parameters.
        and wait for completion

        Validates the provided data using the AgentCreateRequest model, sends a run request through the
        designated endpoint, updates the last agent response, and returns the resulting AgentResponse.
        """
        response = self._start(**data)
        # wait for completion
        max_steps: int = data.get("max_steps", DEFAULT_MAX_NB_STEPS)
        return await self.watch_logs_and_wait(agent_id=response.agent_id, max_steps=max_steps)

    def run_custom(self, request: BaseModel) -> AgentStatusResponse:
        """
        Run an agent with the specified request parameters.
        and wait for completion
        """
        if not self.is_custom_endpoint_available():
            raise ValueError(f"Custom endpoint is not available for this server: {self.server_url}")
        response = self.start_custom(request)
        max_steps = request.model_dump().get("max_steps", max(DEFAULT_MAX_NB_STEPS, 50))
        return asyncio.run(self.watch_logs_and_wait(agent_id=response.agent_id, max_steps=max_steps))

    def _status(self, agent_id: str) -> AgentStatusResponse:
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
        request = AgentStatusRequest(agent_id=agent_id, replay=False)
        endpoint = AgentsClient._agent_status_endpoint(agent_id=agent_id).with_params(request)
        response = self.request(endpoint)
        return response

    def list(self, **data: Unpack[AgentListRequestDict]) -> Sequence[AgentResponse]:
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
        endpoint = AgentsClient._agent_list_endpoint(params=params)
        return self.request_list(endpoint)

    def _replay(self, agent_id: str) -> WebpReplay:
        """
        Downloads the replay for the specified agent in webp format.

        Args:
            agent_id: The identifier of the agent to download the replay for.

        Returns:
            WebpReplay: The replay file in webp format.
        """
        endpoint = AgentsClient._agent_replay_endpoint(agent_id=agent_id)
        file_bytes = self._request_file(endpoint, file_type="webp")
        return WebpReplay(file_bytes)


class RemoteAgent:
    """
    A remote agent that can execute tasks through the Notte API.

    This class provides an interface for running tasks, checking status, and managing replays
    of agent executions. It maintains state about the current agent execution and provides
    methods to interact with the agent through an AgentsClient.

    The agent can be started, monitored, and controlled through various methods. It supports
    both synchronous and asynchronous execution modes, and can provide visual replays of
    its actions in WEBP format.

    Key Features:
    - Start and stop agent execution
    - Monitor agent status and progress
    - Wait for task completion with progress updates
    - Get visual replays of agent actions
    - Support for both sync and async execution

    Attributes:
        request (AgentCreateRequest): The configuration request used to create this agent.
        client (AgentsClient): The client used to communicate with the Notte API.
        response (AgentResponse | None): The latest response from the agent execution.

    Note: This class is designed to work with a single agent instance at a time. For multiple
    concurrent agents, create separate RemoteAgent instances.
    """

    def __init__(
        self,
        client: AgentsClient,
        request: AgentCreateRequest,
        headless: bool,
        open_viewer: Callable[[str], None],
        session: RemoteSession | None = None,
    ) -> None:
        """
        Initialize a new RemoteAgent instance.

        Args:
            client (AgentsClient): The client used to communicate with the Notte API.
            request (AgentCreateRequest): The configuration request for this agent.
        """
        self.headless: bool = headless
        self.open_viewer: Callable[[str], None] = open_viewer
        self.request: AgentCreateRequest = request
        self.client: AgentsClient = client
        self.response: AgentResponse | None = None

    @property
    def agent_id(self) -> str:
        """
        Get the ID of the current agent execution.

        Returns:
            str: The unique identifier of the current agent execution.

        Raises:
            ValueError: If the agent hasn't been run yet (no response available).
        """
        if self.response is None:
            raise ValueError("You need to run the agent first to get the agent id")
        return self.response.agent_id

    def start(self, **data: Unpack[AgentStartRequestDict]) -> AgentResponse:
        """
        Start the agent with the specified request parameters.

        This method initiates the agent execution with the provided configuration.
        The agent will begin processing the task immediately after starting.

        Args:
            **data: Keyword arguments representing the fields of an AgentStartRequest.

        Returns:
            AgentResponse: The initial response from starting the agent.
        """
        self.response = self.client._start(**self.request.model_dump(), **data)  # pyright: ignore[reportPrivateUsage]
        if not self.headless:
            # start viewer
            self.open_viewer(self.response.session_id)
        return self.response

    def start_custom(self, request: BaseModel) -> AgentResponse:
        """
        Start the agent with the specified request parameters.
        """
        self.response = self.client.start_custom(request)
        if not self.headless:
            # start viewer
            self.open_viewer(self.response.session_id)
        return self.response

    def wait(self) -> AgentStatusResponse:
        """
        Wait for the agent to complete its current task.

        This method polls the agent's status at regular intervals until completion.
        During waiting, it displays progress updates and a spinner (in non-notebook environments).
        The polling continues until either the agent completes or a timeout is reached.

        Returns:
            AgentStatusResponse: The final status response after completion.

        Raises:
            TimeoutError: If the agent doesn't complete within the maximum allowed attempts.
        """
        return self.client._wait(agent_id=self.agent_id)  # pyright: ignore [reportPrivateUsage]

    async def watch_logs(self) -> None:
        """
        Watch the logs of the agent.
        """
        return await self.client.watch_logs(agent_id=self.agent_id, max_steps=self.request.max_steps)

    async def watch_logs_and_wait(self) -> AgentStatusResponse:
        """
        Watch the logs of the agent and wait for completion.
        """
        return await self.client.watch_logs_and_wait(agent_id=self.agent_id, max_steps=self.request.max_steps)

    def stop(self) -> AgentResponse:
        """
        Stop the currently running agent.

        This method sends a stop request to the agent, terminating its current execution.
        The agent will stop processing its current task immediately.

        Returns:
            AgentResponse: The response from the stop operation.

        Raises:
            ValueError: If the agent hasn't been run yet (no agent_id available).
        """
        return self.client._stop(agent_id=self.agent_id)  # pyright: ignore [reportPrivateUsage]

    def run(self, **data: Unpack[AgentRunRequestDict]) -> AgentStatusResponse:
        """
        Execute a task with the agent and wait for completion.

        This method combines starting the agent and waiting for its completion in one operation.
        It's the recommended way to run tasks that need to complete before proceeding.

        Args:
            **data: Keyword arguments representing the fields of an AgentRunRequest.

        Returns:
            AgentStatusResponse: The final status response after task completion.

        Raises:
            TimeoutError: If the agent doesn't complete within the maximum allowed attempts.
        """

        return asyncio.run(self.arun(**data))

    async def arun(self, **data: Unpack[AgentRunRequestDict]) -> AgentStatusResponse:
        """
        Asynchronously execute a task with the agent.

        This is currently a wrapper around the synchronous run method.
        In future versions, this might be implemented as a true async operation.

        Args:
            **data: Keyword arguments representing the fields of an AgentRunRequest.

        Returns:
            AgentStatusResponse: The final status response after task completion.
        """
        self.response = self.start(**data)
        logger.info(f"[Agent] {self.agent_id} started")
        return await self.watch_logs_and_wait()

    def run_custom(self, request: BaseModel) -> AgentStatusResponse:
        """
        Run an agent with the specified request parameters.
        and wait for completion
        """
        return self.client.run_custom(request)

    def status(self) -> AgentStatusResponse:
        """
        Get the current status of the agent.

        This method retrieves the current state of the agent, including its progress,
        actions taken, and any errors or messages.

        Returns:
            AgentStatusResponse: The current status of the agent execution.

        Raises:
            ValueError: If the agent hasn't been run yet (no agent_id available).
        """
        return self.client._status(agent_id=self.agent_id)  # pyright: ignore [reportPrivateUsage]

    def replay(self) -> WebpReplay:
        """
        Get a replay of the agent's execution in WEBP format.

        This method downloads a visual replay of the agent's actions, which can be
        useful for debugging or understanding the agent's behavior.

        Returns:
            WebpReplay: The replay data in WEBP format.

        Raises:
            ValueError: If the agent hasn't been run yet (no agent_id available).
        """
        return self.client._replay(agent_id=self.agent_id)  # pyright: ignore [reportPrivateUsage]


@final
class RemoteAgentFactory:
    """
    Factory for creating RemoteAgent instances.

    This factory provides a convenient way to create RemoteAgent instances with
    optional vault and session configurations. It handles the validation of
    agent creation requests and sets up the appropriate connections.

    Attributes:
        client (AgentsClient): The client used to communicate with the Notte API.
    """

    def __init__(self, client: AgentsClient, open_viewer: Callable[[str], None]) -> None:
        """
        Initialize a new RemoteAgentFactory instance.

        Args:
            client (AgentsClient): The client used to communicate with the Notte API.
        """
        self.client = client
        self.open_viewer = open_viewer

    def __call__(
        self,
        headless: bool = False,
        vault: NotteVault | None = None,
        notifier: BaseNotifier | None = None,
        session: RemoteSession | None = None,
        **data: Unpack[AgentCreateRequestDict],
    ) -> RemoteAgent:
        """
        Create a new RemoteAgent instance with the specified configuration.

        This method validates the agent creation request and sets up the appropriate
        connections with the provided vault and session if specified.

        Args:
            headless: Whether to display a live viewer (opened in your browser)
            vault: A notte vault instance, if the agent requires authentication
            session: The session to connect to, if not provided, will start a new one.
            notifier: A notifier (for example, email), which will get called upon task completion.
            session_id: (deprecated) use session instead
            **data: Additional keyword arguments for the agent creation request.

        Returns:
            RemoteAgent: A new RemoteAgent instance configured with the specified parameters.
        """
        request = AgentCreateRequest.model_validate(data)
        if vault is not None:
            if len(vault.vault_id) == 0:
                raise ValueError("Vault ID cannot be empty")
            request.vault_id = vault.vault_id
        if notifier is not None:
            notifier_config = notifier.model_dump()
            request.notifier_config = notifier_config
        if session is not None:
            if len(session.session_id) == 0:
                raise ValueError("Session ID cannot be empty")
            request.session_id = session.session_id
        return RemoteAgent(self.client, request, headless=headless, open_viewer=self.open_viewer)
