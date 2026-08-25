"""`retries=` on execute: re-run a failed action, apply the raise gate to the last attempt."""

from typing import Any

import pytest
from notte_browser.session import NotteSession
from notte_core.errors.actions import ActionExecutionError


@pytest.mark.asyncio
async def test_retries_rerun_a_failed_action_until_it_succeeds() -> None:
    calls = 0

    async def flaky(*_args: Any, **_kwargs: Any) -> bool:
        nonlocal calls
        calls += 1
        return calls >= 3

    async with NotteSession(headless=True) as session:
        session.controller.execute = flaky  # pyright: ignore[reportAttributeAccessIssue, reportMethodAssign]

        result = await session.aexecute(type="wait", time_ms=1, retries=2, retry_delay_ms=0)

    assert result.success is True
    assert calls == 3


@pytest.mark.asyncio
async def test_retries_exhausted_applies_the_raise_gate() -> None:
    calls = 0

    async def failing(*_args: Any, **_kwargs: Any) -> bool:
        nonlocal calls
        calls += 1
        return False

    async with NotteSession(headless=True) as session:
        session.controller.execute = failing  # pyright: ignore[reportAttributeAccessIssue, reportMethodAssign]

        with pytest.raises(ActionExecutionError):
            _ = await session.aexecute(type="wait", time_ms=1, retries=2, retry_delay_ms=0)

    assert calls == 3


@pytest.mark.asyncio
async def test_retries_exhausted_returns_failed_result_when_not_raising() -> None:
    calls = 0

    async def failing(*_args: Any, **_kwargs: Any) -> bool:
        nonlocal calls
        calls += 1
        return False

    async with NotteSession(headless=True) as session:
        session.controller.execute = failing  # pyright: ignore[reportAttributeAccessIssue, reportMethodAssign]

        result = await session.aexecute(type="wait", time_ms=1, retries=1, retry_delay_ms=0, raise_on_failure=False)

    assert result.success is False
    assert calls == 2


@pytest.mark.asyncio
async def test_no_retries_is_a_single_attempt() -> None:
    calls = 0

    async def failing(*_args: Any, **_kwargs: Any) -> bool:
        nonlocal calls
        calls += 1
        return False

    async with NotteSession(headless=True) as session:
        session.controller.execute = failing  # pyright: ignore[reportAttributeAccessIssue, reportMethodAssign]

        result = await session.aexecute(type="wait", time_ms=1, raise_on_failure=False)

    assert result.success is False
    assert calls == 1
