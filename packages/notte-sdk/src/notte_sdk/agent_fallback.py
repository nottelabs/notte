# pyright: reportImportCycles=false
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, Unpack

from loguru import logger
from notte_core.actions import BaseAction
from notte_core.browser.observation import ExecutionResult

from notte_sdk.endpoints.sessions import RemoteSession as NotteSession
from notte_sdk.types import AgentCreateRequestDict, AgentResponse, ExecutionRequestDict

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient

AGENT_FALLBACK_INSTRUCTIONS = """
goal: {task}
instructions:
- if the goal is unclear or ill-defined, fail immediately and ask the user to clarify the goal.
- only performed the required actions to achieve the goal. Don't take any other action not intended to achieve the goal.
- only a few number of actions should be performed.
- don't navigate to any other page/url except if explicitly asked to do so.
context:
- last action failed with error: {error}
"""


class RemoteAgentFallback:
    """
    A context manager that observes a `Session`'s execute calls and triggers an Agent when a step fails.

    Usage:
        with notte.AgentFallback(session, "add to cart") as agent:
            session.execute({"type": "click", "id": "B1"})
            session.execute({"type": "click", "id": "L3"})

    Attributes:
        task: The natural language task of the agent
        steps: List of ExecutionResult for all executions within the agent
        success: Whether all recorded steps succeeded (False if any failed or raised)
        agent_response: The response returned by the spawned agent (if any)
    """

    def __init__(
        self, client: "NotteClient", session: NotteSession, task: str, **agent_params: Unpack[AgentCreateRequestDict]
    ) -> None:
        self.client: "NotteClient" = client
        self.session: NotteSession = session
        self.task: str = task
        self.steps: list[ExecutionResult] = []
        self.success: bool = True
        self.agent_response: AgentResponse | None = None
        self.agent_params: AgentCreateRequestDict = agent_params

        # Saved originals
        self._orig_aexecute: Callable[..., ExecutionResult] | None = None
        self._agent_invoked: bool = False

    # ------------------------ context manager ------------------------
    def __enter__(self) -> "RemoteAgentFallback":
        self._patch_session()
        logger.info(f"📖 agent fallback started: '{self.task}'")
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._restore_session()
        # If a raw exception escaped user code inside the agent fallback
        if exc is not None and not self._agent_invoked:
            logger.error(f"❌ Unhandled exception in agent fallback: {exc}")
            raise exc

        logger.info(
            f"📚 Agent fallback finished: {self.task} | steps={len(self.steps)} | success={self.success} | agent_invoked={self._agent_invoked}"
        )
        # Do not suppress exceptions if any, but none expected since we capture in wrapper
        return None

    # ------------------------ patching logic ------------------------
    def _patch_session(self) -> None:
        # Save original async execute
        self._orig_aexecute = self.session.execute

        # Define wrappers
        def wrapped_execute(
            action: BaseAction | dict[str, Any] | None = None,
            raise_on_failure: bool | None = None,
            **data: Unpack[ExecutionRequestDict],
        ) -> ExecutionResult:
            # Enforce agent fallback constraint
            if raise_on_failure:
                raise ValueError("AgentFallback only supports raise_on_failure=False")
            logger.info(
                f"✏️ AgentFallback executing action: {action.model_dump_agent() if isinstance(action, BaseAction) else action}"
            )
            # Delegate to original aexecute and do not raise on failure
            result = self._orig_aexecute(  # type: ignore[misc]
                action=action, raise_on_failure=False, **data
            )
            # Record and maybe spawn agent
            self._record_step(result)
            if not result.success:
                logger.warning(f"❌ AgentFallback action failed with error: '{result.message}'")
                self._spawn_agent_if_needed()
            return result

        # Monkeypatch only aexecute; execute will route through it
        self.session.execute = wrapped_execute

    def _restore_session(self) -> None:
        if self._orig_aexecute is not None:
            self.session.aexecute = self._orig_aexecute  # type: ignore[assignment]

    # ------------------------ recording & agent ------------------------
    def _record_step(self, result: ExecutionResult) -> None:
        self.steps.append(result)
        if not result.success:
            self.success = False

    def _spawn_agent_if_needed(self) -> None:
        if self._agent_invoked:
            return
        logger.info("🤖 Spawning agent after execution failure...")
        self._agent_invoked = True
        agent = self.client.Agent(session=self.session, **self.agent_params)
        self.agent_response = agent.run(
            task=AGENT_FALLBACK_INSTRUCTIONS.format(task=self.task, error=self.steps[-1].message)
        )
        if self.agent_response.success:
            logger.info("🔥 Agent succeeded in fixing the execution failure")
            self.success = True
        else:
            logger.error(f"❌ Agent failed to fix the execution failure: {self.agent_response.answer}")


class RemoteAgentFallbackFactory:
    def __init__(self, client: "NotteClient") -> None:
        self.client: "NotteClient" = client

    def __call__(
        self, session: NotteSession, task: str, **agent_params: Unpack[AgentCreateRequestDict]
    ) -> RemoteAgentFallback:
        return RemoteAgentFallback(self.client, session, task, **agent_params)
