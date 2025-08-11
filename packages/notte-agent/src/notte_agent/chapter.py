from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from types import TracebackType
from typing import Callable, Unpack

from loguru import logger
from notte_browser.session import NotteSession
from notte_core.actions import BaseAction
from notte_core.browser.observation import ExecutionResult
from notte_core.trajectory import Trajectory
from notte_sdk.types import AgentCreateRequestDict, ExecutionRequestDict

from notte_agent.common.types import AgentResponse
from notte_agent.main import Agent

CHAPTER_INSTRUCTIONS = """
goal: {goal}
instructions:
- if the goal is unclear or ill-defined, fail immediately and ask the user to clarify the goal.
- only performed the required actions to achieve the goal. Don't take any other action not intended to achieve the goal.
- only a few number of actions should be performed.
- don't navigate to any other page/url except if explicitly asked to do so.
context:
- last action failed with error: {error}
"""


class Chapter:
    """
    A context manager that observes a `Session`'s execute calls and triggers an Agent when a step fails.

    Usage:
        with Chapter(session, "add to cart") as chapter:
            session.execute({"type": "click", "id": "B1"})
            session.execute({"type": "click", "id": "L3"})

    Attributes:
        goal: The natural language goal of the chapter
        steps: List of ExecutionResult for all executions within the chapter
        success: Whether all recorded steps succeeded (False if any failed or raised)
        agent_response: The response returned by the spawned agent (if any)
    """

    def __init__(self, session: NotteSession, goal: str, **agent_params: Unpack[AgentCreateRequestDict]) -> None:
        self.session: NotteSession = session
        self.trajectory: Trajectory = session.trajectory.view()
        self.goal: str = goal
        self.steps: list[ExecutionResult] = []
        self.success: bool = True
        self.agent_response: AgentResponse | None = None
        self.agent_params: AgentCreateRequestDict = agent_params

        # Saved originals
        self._orig_aexecute: Callable[..., Awaitable[ExecutionResult]] | None = None
        self._agent_invoked: bool = False

    # ------------------------ context manager ------------------------
    def __enter__(self) -> "Chapter":
        self._patch_session()
        logger.info(f"📖 Chapter started: '{self.goal}'")
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._restore_session()
        # If a raw exception escaped user code inside the chapter
        if exc is not None and not self._agent_invoked:
            logger.error(f"❌ Unhandled exception in chapter: {exc}")
            raise exc

        self._restore_session()
        logger.info(
            f"📚 Chapter finished: {self.goal} | steps={len(self.steps)} | success={self.success} | agent_invoked={self._agent_invoked}"
        )
        # Do not suppress exceptions if any, but none expected since we capture in wrapper
        return None

    # ------------------------ patching logic ------------------------
    def _patch_session(self) -> None:
        # Save original async execute
        self._orig_aexecute = self.session.aexecute

        # Define wrappers
        async def wrapped_aexecute(
            action: BaseAction | None = None,
            raise_exception_on_failure: bool | None = None,
            **data: Unpack[ExecutionRequestDict],
        ) -> ExecutionResult:
            # Enforce chapter constraint
            if raise_exception_on_failure:
                raise ValueError("Chapter only supports raise_exception_on_failure=False")
            logger.info(f"✏️ Chapter executing action: {action.model_dump_agent() if action else data}")
            # Delegate to original aexecute and do not raise on failure
            result = await self._orig_aexecute(  # type: ignore[misc]
                action=action, raise_exception_on_failure=False, **data
            )
            # Record and maybe spawn agent
            self._record_step(result)
            if not result.success:
                logger.warning(f"❌ Chapter action failed with error: '{result.message}'")
                await self._spawn_agent_if_needed_async()
            return result

        # Monkeypatch only aexecute; execute will route through it
        self.session.aexecute = wrapped_aexecute  # type: ignore[assignment]

    def _restore_session(self) -> None:
        if self._orig_aexecute is not None:
            self.session.aexecute = self._orig_aexecute  # type: ignore[assignment]

    # ------------------------ recording & agent ------------------------
    def _record_step(self, result: ExecutionResult) -> None:
        self.steps.append(result)
        if not result.success:
            self.success = False

    def _spawn_agent_if_needed(self) -> None:
        return asyncio.run(self._spawn_agent_if_needed_async())

    async def _spawn_agent_if_needed_async(self) -> None:
        if self._agent_invoked:
            return
        logger.info("🤖 Spawning agent for chapter failure...")
        self._agent_invoked = True
        agent = Agent(session=self.session, trajectory=self.trajectory, **self.agent_params)
        self.agent_response = await agent.arun(
            task=CHAPTER_INSTRUCTIONS.format(goal=self.goal, error=self.steps[-1].message)
        )
        if self.agent_response.success:
            logger.info("🔥 Agent succeeded in fixing the chapter failure")
            self.success = True
        else:
            logger.error(f"❌ Agent failed to fix the chapter failure: {self.agent_response.answer}")
