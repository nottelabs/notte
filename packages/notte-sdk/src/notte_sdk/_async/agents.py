"""Async agents endpoint client for the Notte SDK."""
# pyright: reportImportCycles=false, reportUnusedFunction=false, reportOverlappingOverload=false, reportUnknownVariableType=false, reportUnusedCallResult=false

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import traceback
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Unpack, overload

from notte_core.agent_types import AgentCompletion
from notte_core.common.logging import logger
from notte_core.common.notifier import BaseNotifier
from notte_core.common.telemetry import track_usage
from notte_core.utils.webp_replay import MP4Replay
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import final

from notte_sdk._async.base import AsyncBaseClient, NotteEndpoint
from notte_sdk._async.http import AsyncHTTPClient
from notte_sdk.types import (
    AgentCreateRequest,
    AgentCreateRequestDict,
    AgentFunctionCodeResponse,
    AgentListRequest,
    AgentListRequestDict,
    AgentResponse,
    AgentRunRequest,
    AgentRunRequestDict,
    AgentStatus,
    AgentStatusResponse,
    AgentWorkflowCodeRequest,
    GetFunctionResponse,
    SdkAgentCreateRequest,
    SdkAgentStartRequestDict,
)

# Conditional imports for Pyodide vs native Python
RUNNING_IN_PYODIDE = "pyodide" in sys.modules

if RUNNING_IN_PYODIDE:
    import js  # pyright: ignore[reportMissingImports]
    from pyodide.ffi import create_proxy  # pyright: ignore[reportMissingImports]
else:
    from websockets.asyncio import client

if TYPE_CHECKING:
    from notte_sdk._async.client import AsyncNotteClient
    from notte_sdk._async.personas import AsyncNottePersona
    from notte_sdk._async.sessions import AsyncRemoteSession
    from notte_sdk._async.vaults import AsyncNotteVault
    from notte_sdk._async.workflows import AsyncNotteFunction


class SdkAgentStartRequest(SdkAgentCreateRequest, AgentRunRequest):
    pass


class LegacyAgentStatusResponse(AgentStatusResponse):
    """Handle legacy agent status response format."""

    steps: list[dict[str, Any]] = Field(default_factory=list)


@final
class AsyncAgentsClient(AsyncBaseClient):
    """Async client for agent management."""

    # Endpoints
    AGENT_START = "start"
    AGENT_START_CUSTOM = "start/custom"
    AGENT_STOP = "{agent_id}/stop?session_id={session_id}"
    AGENT_STATUS = "{agent_id}"
    AGENT_FUNCTION = "{agent_id}/workflow/code"
    AGENT_LIST = ""
    AGENT_REPLAY = "{agent_id}/replay"
    AGENT_LOGS_WS = "{agent_id}/debug/logs?token={token}&session_id={session_id}"

    def __init__(
        self,
        root_client: "AsyncNotteClient",
        http_client: AsyncHTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize AsyncAgentsClient."""
        super().__init__(
            root_client=root_client,
            base_endpoint_path="agents",
            http_client=http_client,
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _agent_start_endpoint() -> NotteEndpoint[AgentResponse]:
        return NotteEndpoint(path=AsyncAgentsClient.AGENT_START, response=AgentResponse, method="POST")

    @staticmethod
    def _agent_start_custom_endpoint() -> NotteEndpoint[AgentResponse]:
        # Used by subclasses or future custom agent implementations
        return NotteEndpoint(path=AsyncAgentsClient.AGENT_START_CUSTOM, response=AgentResponse, method="POST")

    @staticmethod
    def _agent_stop_endpoint(
        agent_id: str | None = None, session_id: str | None = None
    ) -> NotteEndpoint[AgentResponse]:
        path = AsyncAgentsClient.AGENT_STOP
        if agent_id is not None:
            path = path.format(agent_id=agent_id, session_id=session_id)
        return NotteEndpoint(path=path, response=AgentStatusResponse, method="DELETE")

    @staticmethod
    def _agent_status_endpoint(agent_id: str | None = None) -> NotteEndpoint[LegacyAgentStatusResponse]:
        path = AsyncAgentsClient.AGENT_STATUS
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=LegacyAgentStatusResponse, method="GET")

    @staticmethod
    def _agent_function_endpoint(agent_id: str | None = None) -> NotteEndpoint[AgentFunctionCodeResponse]:
        path = AsyncAgentsClient.AGENT_FUNCTION
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=AgentFunctionCodeResponse, method="GET")

    @staticmethod
    def _agent_replay_endpoint(agent_id: str | None = None) -> NotteEndpoint[BaseModel]:
        path = AsyncAgentsClient.AGENT_REPLAY
        if agent_id is not None:
            path = path.format(agent_id=agent_id)
        return NotteEndpoint(path=path, response=BaseModel, method="GET")

    @staticmethod
    def _agent_list_endpoint(params: AgentListRequest | None = None) -> NotteEndpoint[AgentResponse]:
        return NotteEndpoint(
            path=AsyncAgentsClient.AGENT_LIST,
            response=AgentResponse,
            method="GET",
            request=None,
            params=params,
        )

    @track_usage("cloud.agent.start")
    async def start(self, **data: Unpack[SdkAgentStartRequestDict]) -> AgentResponse:
        """Start an agent."""
        request = SdkAgentStartRequest.model_validate(data)
        return await self.request(AsyncAgentsClient._agent_start_endpoint().with_request(request))

    @track_usage("cloud.agent.stop")
    async def stop(self, agent_id: str, session_id: str) -> AgentResponse:
        """Stop an agent."""
        logger.info(f"[Agent] {agent_id} is stopping")
        endpoint = AsyncAgentsClient._agent_stop_endpoint(agent_id=agent_id, session_id=session_id)
        response = await self.request(endpoint)
        logger.info(f"[Agent] {agent_id} stopped")
        return response

    @track_usage("cloud.agent.status")
    async def status(self, agent_id: str) -> LegacyAgentStatusResponse:
        """Get agent status."""
        endpoint = AsyncAgentsClient._agent_status_endpoint(agent_id=agent_id)
        return await self.request(endpoint)

    @track_usage("cloud.agent.list")
    async def list(self, **data: Unpack[AgentListRequestDict]) -> Sequence[AgentResponse]:
        """List agents."""
        params = AgentListRequest.model_validate(data)
        endpoint = AsyncAgentsClient._agent_list_endpoint(params=params)
        return await self.request_list(endpoint)

    @track_usage("cloud.agent.replay")
    async def replay(self, agent_id: str) -> MP4Replay:
        """Download the agent replay."""
        endpoint = AsyncAgentsClient._agent_replay_endpoint(agent_id=agent_id)
        file_bytes = await self._request_file(endpoint, file_type="mp4")
        return MP4Replay(file_bytes)

    async def function_code(self, agent_id: str, as_workflow: bool = True) -> AgentFunctionCodeResponse:
        """Get agent function code."""
        request = AgentWorkflowCodeRequest(as_workflow=as_workflow)
        endpoint = AsyncAgentsClient._agent_function_endpoint(agent_id=agent_id).with_params(request)
        return await self.request(endpoint)

    async def create_function(self, agent_id: str) -> GetFunctionResponse:
        """Create a function that reproduces the steps of the specified agent."""
        script = await self.function_code(agent_id, as_workflow=True)
        with tempfile.TemporaryDirectory() as tmp_dir:
            filename = Path(tmp_dir) / "code.py"
            with open(filename, "w") as f:
                _ = f.write(script.python_script)

            return await self.root_client.functions.create(path=str(filename))

    async def wait(
        self,
        agent_id: str,
        polling_interval_seconds: int = 10,
        max_attempts: int = 30,
    ) -> AgentStatusResponse:
        """Wait for the agent to complete by polling status."""
        last_step = 0
        for _ in range(max_attempts):
            response = await self.status(agent_id=agent_id)
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

            await asyncio.sleep(polling_interval_seconds)

        raise TimeoutError("Agent did not complete in time")

    async def watch_logs(self, agent_id: str, session_id: str, log: bool = True) -> AgentStatusResponse | None:
        """Watch the logs of the agent via WebSocket."""
        endpoint = NotteEndpoint(path=AsyncAgentsClient.AGENT_LOGS_WS, response=BaseModel, method="GET")
        wss_url = self.request_path(endpoint).format(agent_id=agent_id, token=self.token, session_id=session_id)
        # Construct full URL
        wss_url = self.server_url.rstrip("/") + wss_url
        wss_url = wss_url.replace("https://", "wss://").replace("http://", "ws://")

        counter = 0

        def process_message(message: str) -> tuple[AgentCompletion | AgentStatusResponse | None, bool]:
            """Process a websocket message. Returns (response, should_stop)."""
            nonlocal counter
            try:
                dic = json.loads(message)
                response = None

                # output from validator
                if isinstance(dic, dict) and "validation" in dic:
                    logger.opt(colors=True).info("<g>{message}</g>", message=dic["validation"])

                # termination message
                elif isinstance(dic, dict) and "status" in dic:
                    if dic["status"] == "agent_stop":
                        if "agent" in dic:
                            agent_status = AgentStatusResponse.model_validate(dic["agent"])
                            return (agent_status, True)
                        return (None, True)

                # actual step
                else:
                    if isinstance(dic, dict):
                        response = AgentCompletion.model_validate(dic)
                    else:
                        logger.warning(f"Expected dict, got {type(dic).__name__}: {message[:200]}")
                        return (None, False)
                    if log:
                        logger.opt(colors=True).info(
                            "Step {counter} (agent: {agent_id})",
                            counter=(counter + 1),
                            agent_id=agent_id,
                        )
                        response.live_log_state()
                    counter += 1

                return (response, False)

            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as e:
                if "error" in message and "last action failed with error" not in message:
                    logger.error(f"Error in agent logs: {e} {agent_id} {message}")
                elif agent_id in message and "agent_id" in message:
                    logger.error(f"Error parsing AgentStatusResponse for message: {message}: {e}")
                else:
                    logger.error(f"Error parsing agent logs for message: {message}: {e}")
                return (None, False)

        if RUNNING_IN_PYODIDE:
            # Use JavaScript WebSocket API via Pyodide FFI
            ws = js.WebSocket.new(wss_url)  # pyright: ignore
            message_queue: asyncio.Queue[str | None] = asyncio.Queue()

            def on_message(event: Any) -> None:
                message_queue.put_nowait(str(event.data))

            def on_error(_event: Any) -> None:
                logger.error("WebSocket error occurred")

            def on_close(_event: Any) -> None:
                message_queue.put_nowait(None)

            on_message_proxy = create_proxy(on_message)  # pyright: ignore
            on_error_proxy = create_proxy(on_error)  # pyright: ignore
            on_close_proxy = create_proxy(on_close)  # pyright: ignore

            ws.addEventListener("message", on_message_proxy)  # pyright: ignore
            ws.addEventListener("error", on_error_proxy)  # pyright: ignore
            ws.addEventListener("close", on_close_proxy)  # pyright: ignore

            while ws.readyState == 0:  # pyright: ignore
                await asyncio.sleep(0.1)

            try:
                while True:
                    message = await message_queue.get()
                    if message is None:
                        break

                    assert isinstance(message, str)
                    response, should_stop = process_message(message)

                    if should_stop:
                        if isinstance(response, AgentStatusResponse):
                            return response
                        return None

            except ConnectionError as e:
                logger.error(f"Connection error: {agent_id} {e}")
                return None
            except Exception as e:
                logger.error(f"Error: {agent_id} {e} {traceback.format_exc()}")
                return None
            finally:
                try:
                    ws.removeEventListener("message", on_message_proxy)  # pyright: ignore
                    ws.removeEventListener("error", on_error_proxy)  # pyright: ignore
                    ws.removeEventListener("close", on_close_proxy)  # pyright: ignore
                except Exception:
                    pass
                on_message_proxy.destroy()  # pyright: ignore
                on_error_proxy.destroy()  # pyright: ignore
                on_close_proxy.destroy()  # pyright: ignore
                ws.close()  # pyright: ignore
        else:
            # Use native Python websockets library
            async with client.connect(  # pyright: ignore[reportPossiblyUnboundVariable]
                uri=wss_url,
                open_timeout=30,
                ping_interval=5,
                ping_timeout=40,
                close_timeout=5,
                max_size=5 * (2**20),
            ) as websocket:
                try:
                    async for message in websocket:
                        assert isinstance(message, str)
                        response, should_stop = process_message(message)

                        if should_stop:
                            if isinstance(response, AgentStatusResponse):
                                return response
                            return None

                except ConnectionError as e:
                    logger.error(f"Connection error: {agent_id} {e}")
                    return None
                except Exception as e:
                    logger.error(f"Error: {agent_id} {e} {traceback.format_exc()}")
                    return None

        return None

    async def watch_logs_and_wait(self, agent_id: str, session_id: str, log: bool = True) -> AgentStatusResponse:
        """Watch logs and wait for the agent to complete."""
        status = None
        try:
            response = await self.watch_logs(agent_id=agent_id, session_id=session_id, log=log)
            if response is not None:
                return response
            logger.warning(f"[Agent] {agent_id} did not return status response. Fetching status as fallback.")
            return await self.status(agent_id=agent_id)

        except asyncio.CancelledError:
            if status is None:
                status = await self.status(agent_id=agent_id)

            if status.status != AgentStatus.closed:
                _ = await self.stop(agent_id=agent_id, session_id=session_id)
            raise

    async def run(self, **data: Unpack[SdkAgentStartRequestDict]) -> AgentStatusResponse:
        """Run an agent and wait for completion."""
        response = await self.start(**data)
        return await self.watch_logs_and_wait(agent_id=response.agent_id, session_id=response.session_id)


@final
class AsyncRemoteAgent:
    """Async remote agent that can execute tasks through the Notte API.

    This class provides an interface for running tasks, checking status, and managing replays
    of agent executions. It maintains state about the current agent execution and provides
    methods to interact with the agent through an AsyncAgentsClient.
    """

    class AsyncAgentWorkflow:
        """Async workflow for agent function code and creation."""

        def __init__(self, client: AsyncAgentsClient, agent_id: str) -> None:
            self.client: AsyncAgentsClient = client
            self.agent_id: str = agent_id

        async def code(self, as_workflow: bool = True) -> AgentFunctionCodeResponse:
            """Get function code that reproduces the agent steps."""
            return await self.client.function_code(self.agent_id, as_workflow=as_workflow)

        async def create_function(self) -> "AsyncNotteFunction":
            """Create a function from the agent's workflow."""
            from notte_sdk._async.workflows import AsyncNotteFunction

            function_resp = await self.client.create_function(self.agent_id)
            return AsyncNotteFunction(function_id=function_resp.function_id, _client=self.client.root_client)

    @overload
    def __init__(
        self,
        session: "AsyncRemoteSession",
        *,
        vault: "AsyncNotteVault | None" = None,
        notifier: BaseNotifier | None = None,
        persona: "AsyncNottePersona | None" = None,
        _client: AsyncAgentsClient | None = None,
        agent_id: str | None = None,
        **data: Unpack[AgentCreateRequestDict],
    ) -> None: ...

    @overload
    def __init__(self, *, agent_id: str, _client: AsyncAgentsClient | None = None) -> None: ...

    def __init__(
        self,
        session: "AsyncRemoteSession | None" = None,
        vault: "AsyncNotteVault | None" = None,
        notifier: BaseNotifier | None = None,
        persona: "AsyncNottePersona | None" = None,
        _client: AsyncAgentsClient | None = None,
        agent_id: str | None = None,
        **data: Unpack[AgentCreateRequestDict],
    ) -> None:
        """Create a new AsyncRemoteAgent instance."""
        if _client is None:
            raise ValueError("AsyncAgentsClient is required")

        if session is None and agent_id is None:
            raise ValueError(
                "Either session (for running a new agent) or agent_id (for accessing an existing agent) have to be provided"
            )

        if session is not None and agent_id is not None:
            raise ValueError(
                "Either session (for running a new agent) or agent_id (for accessing an existing agent) have to be provided, not both"
            )

        existing_agent: bool = agent_id is not None
        self.existing_agent: bool = existing_agent
        self.client: AsyncAgentsClient = _client

        # Initialize response attribute first to avoid redeclaration warning
        self.response: AgentResponse | LegacyAgentStatusResponse | None = None

        if existing_agent:
            # Will be fetched asynchronously
            assert agent_id is not None  # Type narrowing
            self._agent_id: str = agent_id
            self._needs_status_fetch = True
            return

        self._needs_status_fetch = False

        if session is None:
            raise ValueError("Session is required for running a new agent")

        data["session_id"] = session.session_id  # pyright: ignore[reportGeneralTypeIssues]
        request = SdkAgentCreateRequest.model_validate(data)
        if notifier is not None:
            notifier_config = notifier.model_dump()
            request.notifier_config = notifier_config

        if vault is not None:
            if len(vault.vault_id) == 0:
                raise ValueError("Vault ID cannot be empty")
            request.vault_id = vault.vault_id

        if persona is not None:
            if len(persona.persona_id) == 0:
                raise ValueError("Persona ID cannot be empty")
            request.persona_id = persona.persona_id

        if len(session.session_id) == 0:
            raise ValueError("Session ID cannot be empty")
        request.session_id = session.session_id

        self.request: SdkAgentCreateRequest = request

    @property
    def agent_id(self) -> str:
        """Get the ID of the current agent execution."""
        if hasattr(self, "_agent_id") and self._agent_id:
            return self._agent_id
        if self.response is None:
            raise ValueError("You need to run the agent first to get the agent id")
        return self.response.agent_id

    @property
    def session_id(self) -> str:
        """Get the ID of the current session."""
        if self.response is None:
            raise ValueError("You need to run the agent first to get the session id")
        return self.response.session_id

    @track_usage("cloud.agent.start")
    async def start(self, **data: Unpack[AgentRunRequestDict]) -> AgentResponse:
        """Start the agent with the specified request parameters."""
        if self.existing_agent:
            raise ValueError("You cannot call start() on an agent instantiated from agent id")

        self.response = await self.client.start(**self.request.model_dump(), **data)
        return self.response

    async def wait(self) -> AgentStatusResponse:
        """Wait for the agent to complete its current task."""
        if self.existing_agent:
            raise ValueError("You cannot call wait() on an agent instantiated from agent id")

        return await self.client.wait(agent_id=self.agent_id)

    async def watch_logs(self, log: bool = False) -> AgentStatusResponse | None:
        """Watch the logs of the agent."""
        if self.existing_agent:
            raise ValueError("You cannot call watch_logs() on an agent instantiated from agent id")

        return await self.client.watch_logs(agent_id=self.agent_id, session_id=self.session_id, log=log)

    async def watch_logs_and_wait(self, log: bool = True) -> AgentStatusResponse:
        """Watch the logs of the agent and wait for completion."""
        if self.existing_agent:
            raise ValueError("You cannot call watch_logs_and_wait() on an agent instantiated from agent id")

        return await self.client.watch_logs_and_wait(agent_id=self.agent_id, session_id=self.session_id, log=log)

    @track_usage("cloud.agent.stop")
    async def stop(self) -> AgentResponse:
        """Stop the currently running agent."""
        if self.existing_agent:
            raise ValueError("You cannot call stop() on an agent instantiated from agent id")

        return await self.client.stop(agent_id=self.agent_id, session_id=self.session_id)

    @track_usage("cloud.agent.run")
    async def run(self, **data: Unpack[AgentRunRequestDict]) -> AgentStatusResponse:
        """Run an agent with the specified request parameters and wait for completion."""
        if self.existing_agent:
            raise ValueError("You cannot call run() on an agent instantiated from agent id")

        self.response = await self.start(**data)
        logger.info(f"[Agent] {self.agent_id} started with model: {self.request.reasoning_model}")
        status_response = await self.watch_logs_and_wait()
        prefix = "✅ Agent returned with success:" if status_response.success else "❌ Agent returned with failure:"
        logger.info(f"{prefix} {status_response.answer}")
        return status_response

    @track_usage("cloud.agent.status")
    async def status(self) -> LegacyAgentStatusResponse:
        """Get the current status of the agent."""
        return await self.client.status(agent_id=self.agent_id)

    @property
    @track_usage("cloud.agent.workflow")
    def workflow(self) -> AsyncAgentWorkflow:
        """Get the workflow from the completed steps of the agent."""
        return AsyncRemoteAgent.AsyncAgentWorkflow(self.client, self.agent_id)

    @track_usage("cloud.agent.replay")
    async def replay(self) -> MP4Replay:
        """Get a replay of the agent's execution in MP4 format."""
        return await self.client.replay(agent_id=self.agent_id)


@final
class AsyncBatchRemoteAgent:
    """Async batch agent that can execute multiple instances of the same task in parallel.

    This class provides functionality to run multiple agents concurrently with different strategies:
    - "first_success": Returns as soon as any agent succeeds
    - "all_finished": Waits for all agents to complete and returns all results
    """

    def __init__(
        self,
        *,
        session: "AsyncRemoteSession",
        vault: "AsyncNotteVault | None" = None,
        notifier: BaseNotifier | None = None,
        persona: "AsyncNottePersona | None" = None,
        _client: "AsyncNotteClient | None" = None,
        **data: Unpack[AgentCreateRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("AsyncNotteClient is required")
        request = AgentCreateRequest.model_validate(data)
        if notifier is not None:
            notifier_config = notifier.model_dump()
            request.notifier_config = notifier_config

        if vault is not None:
            if len(vault.vault_id) == 0:
                raise ValueError("Vault ID cannot be empty")
            request.vault_id = vault.vault_id

        if persona is not None:
            if len(persona.persona_id) == 0:
                raise ValueError("Persona ID cannot be empty")
            request.persona_id = persona.persona_id

        # Import here to avoid circular imports
        from notte_sdk._async.sessions import AsyncRemoteSession

        if not isinstance(session, AsyncRemoteSession):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("You are trying to use a local session with a remote agent. This is not supported.")  # pyright: ignore[reportUnreachable]
        if session.response is not None:
            raise ValueError(
                "You are trying to pass a started session to AsyncBatchRemoteAgent. AsyncBatchRemoteAgent is only supposed to be provided non-running session, to get the parameters"
            )

        self.request: AgentCreateRequest = request
        self.client: AsyncAgentsClient = _client.agents
        self.root_client: "AsyncNotteClient" = _client
        self.response: AgentResponse | None = None
        self.session: "AsyncRemoteSession" = session

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
        """Run multiple agents in parallel with the specified parameters."""
        from notte_sdk._async.sessions import AsyncRemoteSession

        async def agent_task() -> AgentStatusResponse:
            async with AsyncRemoteSession(
                session_id=self.session.session_id, _client=self.root_client.sessions
            ) as session:
                agent_request = SdkAgentCreateRequest(**self.request.model_dump(), session_id=session.session_id)
                agent = AsyncRemoteAgent(session=session, _client=self.client, **agent_request.model_dump())
                _ = await agent.start(**args)
                return await agent.watch_logs_and_wait(log=False)

        return await AsyncBatchRemoteAgent.run_batch(agent_task, n_jobs=n_jobs, strategy=strategy)

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
        """Internal method to run multiple agents in batch mode."""
        tasks: list[asyncio.Task[AgentStatusResponse]] = []
        results: list[AgentStatusResponse] = []

        for _ in range(n_jobs):
            task = asyncio.create_task(task_creator())
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

        if strategy == "first_success":
            if len(results) > 0:
                return results[0]
            else:
                if exception is None:
                    exception = ValueError(
                        "Every run of the task failed, yet no exception found: this should not happen"
                    )
                raise exception

        return results
