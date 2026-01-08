from collections.abc import Awaitable
from types import TracebackType
from typing import Any, Callable, Unpack

from notte_browser.session import NotteSession
from notte_core.actions import BaseAction
from notte_core.actions.typedicts import parse_action
from notte_core.browser.observation import ExecutionResult
from notte_core.common.logging import logger
from notte_core.trajectory import Trajectory
from notte_sdk.types import AgentCreateRequestDict, ExecutionRequestDict

from notte_agent.common.types import AgentResponse
from notte_agent.main import Agent

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


class AgentFallback:
    """
    A context manager that observes a `Session`'s execute calls and triggers an Agent when a step fails.

    Usage:
    ```python
    with notte.AgentFallback(session=session, task="add to cart") as agent:
        session.execute(actions.Click(id="B1"))
        session.execute(actions.Click(id="L3"))
    ```

    The task is the natural language task of the agent (only to be executed if the steps in the context manager fail).
    """

    def __init__(self, session: NotteSession, task: str, **agent_params: Unpack[AgentCreateRequestDict]) -> None:
        self.session: NotteSession = session
        self.trajectory: Trajectory = session.trajectory.view()
        self.task: str = task
        self.steps: list[ExecutionResult] = []
        self.success: bool = True
        self.agent_response: AgentResponse | None = None
        self.agent_params: AgentCreateRequestDict = agent_params

        # Saved originals
        self._orig_aexecute: Callable[..., Awaitable[ExecutionResult]] | None = None
        self._orig_ascrape: Callable[..., Awaitable[Any]] | None = None
        self._agent_invoked: bool = False

    # ------------------------ context manager ------------------------
    def __enter__(self) -> "AgentFallback":
        self._patch_session()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._restore_session()
        # If a raw exception escaped user code inside the agent fallback
        if exc is not None and not self._agent_invoked:
            logger.error(f"❌ Unhandled exception in agent fallback: {exc}")
            raise exc
        if self._agent_invoked:
            logger.info(
                f"📚 Agent fallback finished: {self.task} | steps={len(self.steps)} | success={self.success} | agent_invoked={self._agent_invoked}"
            )
        # Do not suppress exceptions if any, but none expected since we capture in wrapper
        return None

    # ------------------------ patching logic ------------------------
    def _patch_session(self) -> None:
        # Save original async execute
        self._orig_aexecute = self.session.aexecute
        self._orig_ascrape = self.session.ascrape

        # scrape is not supported inside the context manager
        async def wrapped_ascrape(*args: Any, **kwargs: Any) -> Any:  # pyright: ignore [reportUnusedParameter]
            raise ValueError(
                "Agent fallback does not support scrape. Please use session.scrape outside of the context manager."
            )

        # Define wrappers
        async def wrapped_aexecute(
            action: BaseAction | dict[str, Any] | None = None,
            *,
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

            if self._agent_invoked and self.agent_response is not None:
                logger.warning(f"⚠️ Skipping action: {action_parsed} because agent fallback has been invoked.")
                return ExecutionResult(
                    action=action_parsed,
                    success=True,
                    message="Action skipped because agent fallback has been invoked.",
                    data=None,
                    exception=None,
                )
            # logger.info(f"✏️ Agent fallback executing action: {action_log}")
            # Delegate to original aexecute and do not raise on failure
            result = await self._orig_aexecute(  # type: ignore[misc]
                action=action_parsed, raise_on_failure=False, **data
            )
            # Record and maybe spawn agent
            self._record_step(result)
            if not result.success:
                logger.warning(f"❌ AgentFallback action failed with error: '{result.message}'")
                await self._aspawn_agent_if_needed()
            return result

        # Monkeypatch only aexecute; execute will route through it
        self.session.aexecute = wrapped_aexecute  # pyright: ignore [reportAttributeAccessIssue]
        self.session.ascrape = wrapped_ascrape

    def _restore_session(self) -> None:
        if self._orig_aexecute is not None:
            self.session.aexecute = self._orig_aexecute  # type: ignore[assignment]
        if self._orig_ascrape is not None:
            self.session.ascrape = self._orig_ascrape  # type: ignore[assignment]

    # ------------------------ recording & agent ------------------------
    def _record_step(self, result: ExecutionResult) -> None:
        self.steps.append(result)
        if not result.success:
            self.success = False

    async def _aspawn_agent_if_needed(self) -> None:
        if self._agent_invoked:
            return
        logger.info(f"🤖 Spawning agent fallback after execution failure with task: {self.task}")
        self._agent_invoked = True
        agent = Agent(session=self.session, trajectory=self.trajectory, **self.agent_params)
        self.agent_response = await agent.arun(
            task=AGENT_FALLBACK_INSTRUCTIONS.format(task=self.task, error=self.steps[-1].message)
        )
        if self.agent_response.success:
            logger.info("🔥 Agent succeeded in fixing the execution failure")
            self.success = True
        else:
            logger.error(f"❌ Agent failed to fix the execution failure: {self.agent_response.answer}")
