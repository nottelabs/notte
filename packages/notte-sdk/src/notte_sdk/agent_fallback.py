# pyright: reportImportCycles=false
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, Unpack

from notte_core.actions import BaseAction
from notte_core.actions.typedicts import parse_action
from notte_core.browser.observation import ExecutionResult
from notte_core.common.logging import logger

from notte_sdk.endpoints.agents import RemoteAgent
from notte_sdk.endpoints.sessions import RemoteSession as NotteSession
from notte_sdk.types import AgentCreateRequestDict, AgentStatusResponse, ExecutionRequestDict

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
        ```python
        with notte.AgentFallback(session, "add to cart") as agent:
            session.execute(actions.Click(id="B1"))
            session.execute(actions.Click(id="L3"))
        ```

    Attributes:
        task: The natural language task of the agent
        steps: List of ExecutionResult for all executions within the agent
        success: Whether all recorded steps succeeded (False if any failed or raised)
        agent_response: The response returned by the spawned agent (if any)
    """

    def __init__(
        self,
        session: NotteSession,
        task: str,
        _client: "NotteClient | None" = None,
        **agent_params: Unpack[AgentCreateRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("_client argument cannot be None")
        self.client: "NotteClient" = _client
        self.session: NotteSession = session
        self.task: str = task
        self.steps: list[ExecutionResult] = []
        self.success: bool = True
        self.agent_response: AgentStatusResponse | None = None
        self.agent_params: AgentCreateRequestDict = agent_params
        self.session_offset: int | None = None

        # Saved originals
        self._orig_execute: Callable[..., ExecutionResult] | None = None
        self._orig_scrape: Callable[..., Any] | None = None
        self._agent: RemoteAgent | None = None

    # ------------------------ context manager ------------------------
    def __enter__(self) -> "RemoteAgentFallback":
        self._patch_session()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._restore_session()
        # If a raw exception escaped user code inside the agent fallback
        if exc is not None and not self.agent_invoked:
            logger.error(f"❌ Unhandled exception in agent fallback: {exc}")
            raise exc

        if self.agent_invoked:
            logger.info(
                f"📚 Agent fallback finished: {self.task} | steps={len(self.steps)} | success={self.success} | agent_invoked={self.agent_invoked}"
            )
        # Do not suppress exceptions if any, but none expected since we capture in wrapper
        return None

    @property
    def agent_invoked(self) -> bool:
        return self._agent is not None

    # ------------------------ patching logic ------------------------
    def _patch_session(self) -> None:
        # Save execute
        self._orig_execute = self.session.execute
        self._orig_scrape = self.session.scrape
        self.session_offset = self.session.offset()

        # scrape is not supported inside the context manager
        def wrapped_scrape(*args: Any, **kwargs: Any) -> Any:  # pyright: ignore [reportUnusedParameter]
            raise ValueError(
                "Agent fallback does not support scrape. Please use session.scrape outside of the context manager."
            )

        # Define wrappers
        def wrapped_execute(
            action: BaseAction | dict[str, Any] | None = None,
            raise_on_failure: bool | None = None,
            **data: Unpack[ExecutionRequestDict],
        ) -> ExecutionResult:
            # Enforce agent fallback constraint
            if raise_on_failure:
                raise ValueError("AgentFallback only supports raise_on_failure=False")

            if isinstance(action, dict):
                action_parsed = parse_action(**action, **data)
            else:
                action_parsed = parse_action(action, **data)

            if self.agent_invoked and self.agent_response is not None:
                logger.warning(f"⚠️ Skipping action: {action_parsed} because agent fallback has been invoked.")

                return ExecutionResult(
                    action=action_parsed,
                    success=True,
                    message="Action skipped because agent fallback has been invoked.",
                    data=None,
                    exception=None,
                )
            # logger.info(f"✏️ Agent fallback executing action: {action_log}")
            # Delegate to original execute and do not raise on failure
            result = self._orig_execute(  # type: ignore
                action=action_parsed, raise_on_failure=False, **data
            )
            # Record and maybe spawn agent
            self._record_step(result)
            if not result.success:
                logger.warning(f"❌ AgentFallback action failed with error: '{result.message}'")
                self._spawn_agent_if_needed()
            return result

        self.session.execute = wrapped_execute  # pyright: ignore [reportAttributeAccessIssue]
        self.session.scrape = wrapped_scrape

    def _restore_session(self) -> None:
        if self._orig_execute is not None:
            self.session.execute = self._orig_execute
        if self._orig_scrape is not None:
            self.session.scrape = self._orig_scrape

    # ------------------------ recording & agent ------------------------
    def _record_step(self, result: ExecutionResult) -> None:
        self.steps.append(result)
        if not result.success:
            self.success = False

    def _spawn_agent_if_needed(self) -> None:
        logger.info(f"🤖 Spawning agent fallback after execution failure with task: {self.task}")
        self._agent = self.client.Agent(session=self.session, **self.agent_params)
        self.agent_response = self._agent.run(
            task=AGENT_FALLBACK_INSTRUCTIONS.format(task=self.task, error=self.steps[-1].message),
            session_offset=self.session_offset,
        )
        if self.agent_response.success:
            logger.info("🔥 Agent succeeded in fixing the execution failure")
            self.success = True
        else:
            logger.error(f"❌ Agent failed to fix the execution failure: {self.agent_response.answer}")
