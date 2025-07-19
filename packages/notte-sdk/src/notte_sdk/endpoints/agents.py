import asyncio
import time
import traceback
from abc import ABC
from collections.abc import Coroutine, Sequence
from typing import TYPE_CHECKING, Any, Callable, Literal, Unpack, overload

from halo import Halo  # pyright: ignore[reportMissingTypeStubs]
from loguru import logger
from notte_core.agent_types import AgentCompletion
from notte_core.common.notifier import BaseNotifier
from notte_core.common.telemetry import track_usage
from notte_core.utils.webp_replay import WebpReplay
from pydantic import BaseModel, Field
from typing_extensions import final, override
from websockets.asyncio import client

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.endpoints.vaults import NotteVault
from notte_sdk.types import (
    AgentCreateRequest,
    AgentCreateRequestDict,
    AgentListRequest,
    AgentListRequestDict,
    AgentResponse,
    AgentRunRequest,
    AgentRunRequestDict,
    AgentStatus,
    AgentStatusRequest,
    AgentStatusResponse,
    SdkAgentCreateRequest,
    SdkAgentStartRequestDict,
)

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


class SdkAgentStartRequest(SdkAgentCreateRequest, AgentRunRequest):
    pass


class LegacyAgentStatusResponse(AgentStatusResponse):
    """
    This class is used to handle the legacy agent status response.
    The rationale is that we are likely to change the `AgentStepResponse` in the future and we want to be able to handle the legacy response.
    This is a temporary solution to avoid breaking changes.
    """

    steps: list[dict[str, Any]] = Field(default_factory=list)  # pyright: ignore[reportIncompatibleVariableOverride]


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
    AGENT_STOP = "{agent_id}/stop?session_id={session_id}"
    AGENT_STATUS = "{agent_id}"
    AGENT_LIST = ""
    # The following endpoints downloads a .webp file
    AGENT_REPLAY = "{agent_id}/replay"
    AGENT_LOGS_WS = "{agent_id}/debug/logs?token={token}&session_id={session_id}"

    def __init__(
        self,
        root_client: "NotteClient",
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
        super().__init__(
            root_client=root_client,
            base_endpoint_path="agents",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

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
    def _agent_stop_endpoint(
        agent_id: str | None = None, session_id: str | None = None
    ) -> NotteEndpoint[AgentResponse]:
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
            path = path.format(agent_id=agent_id, session_id=session_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="DELETE")

    @staticmethod
    def _agent_status_endpoint(agent_id: str | None = None) -> NotteEndpoint[LegacyAgentStatusResponse]:
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
        return NotteEndpoint(path=path, response=LegacyAgentStatusResponse, method="GET")

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

    def start(self, **data: Unpack[SdkAgentStartRequestDict]) -> AgentResponse:
        """
        Start an agent with the specified request parameters.

        Validates the provided data using the AgentRunRequest model, sends a run request through the
        designated endpoint, updates the last agent response, and returns the resulting AgentResponse.

        Args:
            **data: Keyword arguments representing the fields of an AgentRunRequest.

        Returns:
            AgentResponse: The response obtained from the agent run request.
        """
        request = SdkAgentStartRequest.model_validate(data)
        response = self.request(AgentsClient._agent_start_endpoint().with_request(request))
        return response

    def wait(
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
            response = self.status(agent_id=agent_id)
            if len(response.steps) > last_step:
                for _step in response.steps[last_step:]:
                    step = AgentCompletion.model_validate(_step)
                    step.live_log_state()
                    if step.is_completed():
                        logger.info(f"Agent {agent_id} completed in {len(response.steps)} steps")
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

    async def watch_logs(self, agent_id: str, session_id: str, log: bool = True) -> AgentStatusResponse | None:
        """
        Watch the logs of the specified agent.
        """
        endpoint = NotteEndpoint(path=AgentsClient.AGENT_LOGS_WS, response=BaseModel, method="GET")
        wss_url = self.request_path(endpoint).format(agent_id=agent_id, token=self.token, session_id=session_id)
        wss_url = wss_url.replace("https://", "wss://").replace("http://", "ws://")

        async def get_messages() -> AgentStatusResponse | None:
            counter = 0
            async with client.connect(
                uri=wss_url,
                open_timeout=30,
                ping_interval=5,
                ping_timeout=40,
                close_timeout=5,
            ) as websocket:
                try:
                    async for message in websocket:
                        assert isinstance(message, str), f"Expected str, got {type(message)}"
                        try:
                            if agent_id in message and "agent_id" in message:
                                # termination condition
                                return AgentStatusResponse.model_validate_json(message)
                            response = AgentCompletion.model_validate_json(message)
                            if log:
                                logger.opt(colors=True).info(
                                    "✨ <r>Step {counter}</r> <y>(agent: {agent_id})</y>",
                                    counter=(counter + 1),
                                    agent_id=agent_id,
                                )
                                response.live_log_state()
                            counter += 1
                        except Exception as e:
                            if "error" in message:
                                logger.error(f"Error in agent logs: {agent_id} {message}")
                            elif agent_id in message and "agent_id" in message:
                                logger.error(f"Error parsing AgentStatusResponse for message: {message}: {e}")
                            else:
                                logger.error(f"Error parsing agent logs for message: {message}: {e}")
                            continue

                        if response.is_completed():
                            logger.info(f"Agent {agent_id} completed in {counter} steps")

                except ConnectionError as e:
                    logger.error(f"Connection error: {agent_id} {e}")
                    return
                except Exception as e:
                    logger.error(f"Error: {agent_id} {e} {traceback.format_exc()}")
                    return

        return await get_messages()

    async def watch_logs_and_wait(self, agent_id: str, session_id: str, log: bool = True) -> AgentStatusResponse:
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
        status = None
        try:
            response = await self.watch_logs(agent_id=agent_id, session_id=session_id, log=log)
            if response is not None:
                return response
            # Wait max 9 seconds for the agent to complete
            TOTAL_WAIT_TIME, ITERATIONS = 9, 3
            for _ in range(ITERATIONS):
                time.sleep(TOTAL_WAIT_TIME / ITERATIONS)
                status = self.status(agent_id=agent_id)
                return status
            time.sleep(TOTAL_WAIT_TIME)
            logger.error(
                f"[Agent] {agent_id} failed to complete in time. Try running `agent.status()` after a few seconds."
            )
            return self.status(agent_id=agent_id)

        except asyncio.CancelledError:
            if status is None:
                status = self.status(agent_id=agent_id)

            if status.status != AgentStatus.closed:
                _ = self.stop(agent_id=agent_id, session_id=session_id)
            raise

    def stop(self, agent_id: str, session_id: str) -> AgentResponse:
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
        logger.info(f"[Agent] {agent_id} is stopping")
        endpoint = AgentsClient._agent_stop_endpoint(agent_id=agent_id, session_id=session_id)
        response = self.request(endpoint)
        logger.info(f"[Agent] {agent_id} stopped")
        return response

    def run(self, **data: Unpack[SdkAgentStartRequestDict]) -> AgentStatusResponse:
        """
        Run an agent with the specified request parameters.
        and wait for completion

        Validates the provided data using the AgentCreateRequest model, sends a run request through the
        designated endpoint, updates the last agent response, and returns the resulting AgentResponse.
        """
        return asyncio.run(self.arun(**data))

    async def arun(self, **data: Unpack[SdkAgentStartRequestDict]) -> AgentStatusResponse:
        """
        Run an async agent with the specified request parameters.
        and wait for completion

        Validates the provided data using the AgentCreateRequest model, sends a run request through the
        designated endpoint, updates the last agent response, and returns the resulting AgentResponse.
        """
        response = self.start(**data)
        # wait for completion
        return await self.watch_logs_and_wait(
            agent_id=response.agent_id,
            session_id=response.session_id,
        )

    def status(self, agent_id: str) -> LegacyAgentStatusResponse:
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

    def replay(self, agent_id: str) -> WebpReplay:
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

    async def arun_custom(
        self, request: BaseModel, parallel_attempts: int = 1, viewer: bool = False
    ) -> AgentStatusResponse:
        if not self.is_custom_endpoint_available():
            raise ValueError(f"Custom endpoint is not available for this server: {self.server_url}")

        async def agent_task() -> AgentStatusResponse:
            response = self.request(AgentsClient._agent_start_custom_endpoint().with_request(request))

            if viewer:
                self.root_client.sessions.viewer(response.session_id)

            return await self.watch_logs_and_wait(
                agent_id=response.agent_id,
                session_id=response.session_id,
                log=True,
            )

        return await BatchAgent.run_batch(agent_task, n_jobs=parallel_attempts, strategy="first_success")

    def run_custom(self, request: BaseModel, parallel_attempts: int = 1, viewer: bool = False) -> AgentStatusResponse:
        """
        Run an custom agent with the specified request parameters.
        and wait for completion

        Note: not all servers support custom agents.
        """
        return asyncio.run(self.arun_custom(request, parallel_attempts=parallel_attempts, viewer=viewer))


class BatchAgent:
    """
    A batch agent that can execute multiple instances of the same task in parallel.

    This class provides functionality to run multiple agents concurrently with different strategies:
    - "first_success": Returns as soon as any agent succeeds
    - "all_finished": Waits for all agents to complete and returns all results

    The batch agent is useful for tasks that may have non-deterministic outcomes or
    when you want to try multiple attempts in parallel to improve success rates.

    Attributes:
        headless (bool): Whether to run the agents in headless mode
        request (_AgentCreateRequest): The base configuration request for all agents
        client (AgentsClient): The client used to communicate with the Notte API
        response (AgentResponse | None): The latest response from any agent execution
    """

    def __init__(
        self,
        client: AgentsClient,
        session: RemoteSession,
        request: AgentCreateRequest,
    ) -> None:
        """
        Initialize a new BatchAgent instance.

        Args:
            client: The client used to communicate with the Notte API
            request: The base configuration request for all agents
            session: Optional remote session to use (Note: sessions are not shared between batch agents)
        """
        self.request: AgentCreateRequest = request
        self.client: AgentsClient = client
        self.response: AgentResponse | None = None
        self.session: RemoteSession = session

    @overload
    async def run(
        self,
        n_jobs: int = 2,
        strategy: Literal["first_success"] = "first_success",
        **args: Unpack[AgentRunRequestDict],
    ) -> AgentStatusResponse: ...
    @overload
    async def run(
        self,
        n_jobs: int = 2,
        strategy: Literal["all_finished"] = "all_finished",
        **args: Unpack[AgentRunRequestDict],
    ) -> list[AgentStatusResponse]: ...
    async def run(
        self,
        n_jobs: int = 2,
        strategy: Literal["all_finished", "first_success"] = "first_success",
        **args: Unpack[AgentRunRequestDict],
    ) -> AgentStatusResponse | list[AgentStatusResponse]:
        """
        Run multiple agents in parallel with the specified parameters.

        Args:
            n_jobs: Number of parallel agents to run
            strategy: The execution strategy:
                     - "first_success": Return as soon as any agent succeeds
                     - "all_finished": Wait for all agents to complete
            **args: Additional arguments passed to each agent's start method

        Returns:
            If strategy is "first_success": The first successful AgentStatusResponse
            If strategy is "all_finished": List of all AgentStatusResponse objects
        """

        async def agent_task() -> AgentStatusResponse:
            agent = None

            with RemoteSession(self.session.client, self.session.request) as session:
                agent_request = SdkAgentCreateRequest(**self.request.model_dump(), session_id=session.session_id)

                agent = RemoteAgent(self.client, agent_request)
                _ = agent.start(**args)
                return await agent.watch_logs_and_wait(log=False)

        return await BatchAgent.run_batch(
            agent_task,
            n_jobs=n_jobs,
            strategy=strategy,
        )

    @overload
    @staticmethod
    async def run_batch(
        task_creator: Callable[[], Coroutine[Any, Any, AgentStatusResponse]],
        n_jobs: int = 2,
        strategy: Literal["first_success"] = "first_success",
    ) -> AgentStatusResponse: ...
    @overload
    @staticmethod
    async def run_batch(
        task_creator: Callable[[], Coroutine[Any, Any, AgentStatusResponse]],
        n_jobs: int = 2,
        strategy: Literal["all_finished"] = "all_finished",
    ) -> list[AgentStatusResponse]: ...
    @staticmethod
    async def run_batch(
        task_creator: Callable[[], Coroutine[Any, Any, AgentStatusResponse]],
        n_jobs: int = 2,
        strategy: Literal["all_finished", "first_success"] = "first_success",
    ) -> AgentStatusResponse | list[AgentStatusResponse]:
        """
        Internal method to run multiple agents in batch mode.

        Args:
            request_type: Type of request ("default" or "custom")
            request: The request parameters for each agent
            n_jobs: Number of parallel agents to run
            strategy: The execution strategy:
                     - "first_success": Return as soon as any agent succeeds
                     - "all_finished": Wait for all agents to complete

        Returns:
            If strategy is "first_success": The first successful AgentStatusResponse
            If strategy is "all_finished": List of all AgentStatusResponse objects
        """
        tasks: list[asyncio.Task[AgentStatusResponse]] = []
        results: list[AgentStatusResponse] = []

        for _ in range(n_jobs):
            task = asyncio.Task(task_creator())
            tasks.append(task)

        exception = None
        for completed_task in asyncio.as_completed(tasks):
            try:
                result = await completed_task

                if result.success and strategy == "first_success":
                    for task in tasks:
                        if not task.done():
                            _ = task.cancel()

                    return result
                else:
                    results.append(result)
            except Exception as e:
                exception = e
                logger.error(
                    f"Batch task failed: {exception.__class__.__qualname__} {exception} {traceback.format_exc()}"
                )
                continue

        # if first success, all failed, can just return any
        if strategy == "first_success":
            if len(results) > 0:
                result = results[0]
                return result
            else:
                if exception is None:
                    exception = ValueError(
                        "Every run of the task failed, yet no exception found: this should not happen"
                    )
                raise exception

        # all finished, return the list
        return results


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
        request: SdkAgentCreateRequest,
    ) -> None:
        """
        Initialize a new RemoteAgent instance.

        Args:
            client (AgentsClient): The client used to communicate with the Notte API.
            request (AgentCreateRequest): The configuration request for this agent.
        """
        self.request: SdkAgentCreateRequest = request
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

    @property
    def session_id(self) -> str:
        """
        Get the ID of the current session.
        """
        if self.response is None:
            raise ValueError("You need to run the agent first to get the session id")
        return self.response.session_id

    @track_usage("cloud.agent.start")
    def start(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        """
        Start the agent with the specified request parameters.

        This method initiates the agent execution with the provided configuration.
        The agent will begin processing the task immediately after starting.

        Args:
            **data: Keyword arguments representing the fields of an AgentStartRequest.

        Returns:
            AgentResponse: The initial response from starting the agent.
        """
        self.response = self.client.start(**self.request.model_dump(), **data)
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
        return self.client.wait(agent_id=self.agent_id)

    async def watch_logs(self, log: bool = False) -> AgentStatusResponse | None:
        """
        Watch the logs of the agent.
        """
        return await self.client.watch_logs(agent_id=self.agent_id, session_id=self.session_id, log=log)

    async def watch_logs_and_wait(self, log: bool = True) -> AgentStatusResponse:
        """
        Watch the logs of the agent and wait for completion.
        """
        return await self.client.watch_logs_and_wait(agent_id=self.agent_id, session_id=self.session_id, log=log)

    @track_usage("cloud.agent.stop")
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
        return self.client.stop(agent_id=self.agent_id, session_id=self.session_id)

    @track_usage("cloud.agent.run")
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

    @track_usage("cloud.agent.arun")
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
        logger.info(f"[Agent] {self.agent_id} started with model: {self.request.reasoning_model}")
        return await self.watch_logs_and_wait()

    @track_usage("cloud.agent.status")
    def status(self) -> LegacyAgentStatusResponse:
        """
        Get the current status of the agent.

        This method retrieves the current state of the agent, including its progress,
        actions taken, and any errors or messages.

        Returns:
            LegacyAgentStatusResponse: The current status of the agent execution.

        Raises:
            ValueError: If the agent hasn't been run yet (no agent_id available).
        """
        return self.client.status(agent_id=self.agent_id)

    @track_usage("cloud.agent.replay")
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
        return self.client.replay(agent_id=self.agent_id)


class AgentFactory(ABC):
    """
    Factory for creating RemoteAgent instances.

    This factory provides a convenient way to create RemoteAgent instances with
    optional vault and session configurations. It handles the validation of
    agent creation requests and sets up the appropriate connections.

    Attributes:
        client (AgentsClient): The client used to communicate with the Notte API.
    """

    def __init__(self, client: AgentsClient) -> None:
        """
        Initialize a new RemoteAgentFactory instance.

        Args:
            client (AgentsClient): The client used to communicate with the Notte API.
        """
        self.client: AgentsClient = client

    def __call__(
        self,
        session: RemoteSession,
        vault: NotteVault | None = None,
        notifier: BaseNotifier | None = None,
        **data: Unpack[AgentCreateRequestDict],
    ) -> BatchAgent | RemoteAgent:
        raise NotImplementedError


class RemoteAgentFactory(AgentFactory):
    def __init__(self, client: AgentsClient) -> None:
        """
        Initialize a new RemoteAgentFactory instance.

        A factory for creating single RemoteAgent instances. This factory ensures that agents
        are created with non-batch mode enabled.

        Args:
            client: The client used to communicate with the Notte API.
        """
        super().__init__(client)

    @override
    def __call__(
        self,
        session: RemoteSession,
        vault: NotteVault | None = None,
        notifier: BaseNotifier | None = None,
        **data: Unpack[AgentCreateRequestDict],
    ) -> RemoteAgent:
        """
        Create a new RemoteAgent instance with the specified configuration.

        This method validates the agent creation request and sets up the appropriate
        connections with the provided vault and session if specified.

        Args:
            headless: Whether to display a live viewer (opened in your browser)
            vault: A notte vault instance, if the agent requires authentication
            session: The session to connect to.
            notifier: A notifier (for example, email), which will get called upon task completion.
            session_id: (deprecated) use session instead
            **data: Additional keyword arguments for the agent creation request.

        Returns:
            RemoteAgent: A new RemoteAgent instance configured with the specified parameters.
        """
        data["session_id"] = session.session_id  # pyright: ignore[reportGeneralTypeIssues]
        request = SdkAgentCreateRequest.model_validate(data)
        if notifier is not None:
            notifier_config = notifier.model_dump()
            request.notifier_config = notifier_config

        # #########################################################
        # ###################### Vault checks #####################
        # #########################################################

        if vault is not None:
            if len(vault.vault_id) == 0:
                raise ValueError("Vault ID cannot be empty")
            request.vault_id = vault.vault_id

        # #########################################################
        # #################### Session checks #####################
        # #########################################################

        if not isinstance(session, RemoteSession):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError(
                "You are trying to use a local session with a remote agent. This is not supported. Use `notte.Agent(session=session)` instead."
            )  # pyright: ignore[reportUnreachable]
        if len(session.session_id) == 0:
            raise ValueError("Session ID cannot be empty")
        request.session_id = session.session_id

        return RemoteAgent(self.client, request)


class BatchAgentFactory(AgentFactory):
    def __init__(self, client: AgentsClient) -> None:
        """
        Initialize a new BatchAgentFactory instance.

        A factory for creating BatchAgent instances that can run multiple agents in parallel.
        This factory ensures that agents are created with batch mode enabled.

        Args:
            client: The client used to communicate with the Notte API.
        """
        super().__init__(client)

    @override
    def __call__(
        self,
        session: RemoteSession,
        vault: NotteVault | None = None,
        notifier: BaseNotifier | None = None,
        raise_on_existing_contextual_session: bool = True,
        **data: Unpack[AgentCreateRequestDict],
    ) -> BatchAgent:
        request = AgentCreateRequest.model_validate(data)
        if notifier is not None:
            notifier_config = notifier.model_dump()
            request.notifier_config = notifier_config

        # #########################################################
        # ###################### Vault checks #####################
        # #########################################################

        if vault is not None:
            if len(vault.vault_id) == 0:
                raise ValueError("Vault ID cannot be empty")
            request.vault_id = vault.vault_id

        # #########################################################
        # #################### Session checks #####################
        # #########################################################
        if not isinstance(session, RemoteSession):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError(
                "You are trying to use a local session with a remote agent. This is not supported. Use `notte.Agent(session=session)` instead."
            )  # pyright: ignore[reportUnreachable]
        if session.response is not None:
            raise ValueError(
                "You are trying to pass a started session to BatchAgent. BatchAgent is only supposed to be provided non-running session, to get the parameters"
            )

        return BatchAgent(self.client, session, request)
