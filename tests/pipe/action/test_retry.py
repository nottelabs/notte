from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from notte_browser.tagging.action.llm_taging.base import BaseActionListingPipe, RetryPipeWrapper
from notte_browser.tagging.type import PossibleAction, PossibleActionSpace
from notte_core.actions import ClickAction
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.errors.llm import ContextSizeTooLargeError
from notte_core.errors.provider import ContextWindowExceededError

from tests.mock.mock_service import MockLLMService


def make_wrapper(
    *,
    incremental_side_effect: object | None = None,
    forward_side_effect: object | None = None,
    max_tries: int = 3,
    verbose: bool = False,
) -> tuple[RetryPipeWrapper, MagicMock]:
    pipe = MagicMock(spec=BaseActionListingPipe)
    pipe.llmserve = MockLLMService(mock_response="")
    pipe.forward_incremental = AsyncMock(side_effect=incremental_side_effect)
    pipe.forward = AsyncMock(side_effect=forward_side_effect)
    return (
        RetryPipeWrapper(
            pipe=cast(BaseActionListingPipe, pipe),
            max_tries=max_tries,
            verbose=verbose,
        ),
        pipe,
    )


def previous_actions() -> list[ClickAction]:
    return [
        ClickAction(
            id="B1",
            description="Click the button",
            category="Interaction Actions",
        )
    ]


@pytest.mark.asyncio
async def test_incremental_retry_traces_recovery() -> None:
    expected = PossibleActionSpace(
        description="Recovered",
        actions=[PossibleAction(id="B2", description="Click another button", category="Interaction Actions")],
    )
    wrapper, pipe = make_wrapper(incremental_side_effect=[ValueError("invalid response"), expected])
    tracer = MagicMock()

    with patch.object(RetryPipeWrapper, "tracer", tracer):
        result = await wrapper.forward_incremental(
            snapshot=MagicMock(spec=BrowserSnapshot),
            previous_action_list=previous_actions(),
        )

    assert result is expected
    assert pipe.forward_incremental.await_count == 2
    tracer.trace.assert_called_once_with(
        status="success",
        pipe_name="BaseActionListingPipe",
        nb_retries=1,
        error_msgs=["invalid response"],
    )


@pytest.mark.asyncio
async def test_incremental_retry_logs_and_traces_fallback() -> None:
    wrapper, pipe = make_wrapper(
        incremental_side_effect=ValueError("invalid response"),
        max_tries=2,
        verbose=True,
    )
    tracer = MagicMock()

    with (
        patch.object(RetryPipeWrapper, "tracer", tracer),
        patch("notte_browser.tagging.action.llm_taging.base.logger") as logger,
    ):
        result = await wrapper.forward_incremental(
            snapshot=MagicMock(spec=BrowserSnapshot),
            previous_action_list=previous_actions(),
        )

    assert [action.id for action in result.actions] == ["B1"]
    assert pipe.forward_incremental.await_count == 2
    assert logger.opt.call_count == 2
    logger.opt.assert_called_with(exception=True)
    assert logger.opt.return_value.debug.call_count == 2
    tracer.trace.assert_called_once_with(
        status="failure",
        pipe_name="BaseActionListingPipe",
        nb_retries=2,
        error_msgs=["invalid response", "invalid response"],
    )


@pytest.mark.asyncio
async def test_incremental_context_size_failure_skips_pointless_retries() -> None:
    error = RuntimeError(
        "Please reduce the length of the messages or completions. Current length is 200 while limit is 100"
    )
    wrapper, pipe = make_wrapper(incremental_side_effect=error, max_tries=3)
    tracer = MagicMock()

    with patch.object(RetryPipeWrapper, "tracer", tracer):
        result = await wrapper.forward_incremental(
            snapshot=MagicMock(spec=BrowserSnapshot),
            previous_action_list=previous_actions(),
        )

    assert [action.id for action in result.actions] == ["B1"]
    assert pipe.forward_incremental.await_count == 1
    tracer.trace.assert_called_once_with(
        status="failure",
        pipe_name="BaseActionListingPipe",
        nb_retries=1,
        error_msgs=[str(error)],
    )


@pytest.mark.asyncio
async def test_incremental_typed_context_size_failure_skips_pointless_retries() -> None:
    error = ContextSizeTooLargeError(size=200, max_size=100)
    wrapper, pipe = make_wrapper(incremental_side_effect=error, max_tries=3)

    with patch.object(RetryPipeWrapper, "tracer", MagicMock()):
        result = await wrapper.forward_incremental(
            snapshot=MagicMock(spec=BrowserSnapshot),
            previous_action_list=previous_actions(),
        )

    assert [action.id for action in result.actions] == ["B1"]
    assert pipe.forward_incremental.await_count == 1


@pytest.mark.asyncio
async def test_engine_context_window_failure_skips_pointless_retries() -> None:
    error = ContextWindowExceededError(provider="test/model", current_size=200, max_size=100)
    wrapper, pipe = make_wrapper(incremental_side_effect=error, max_tries=3)

    with patch.object(RetryPipeWrapper, "tracer", MagicMock()):
        result = await wrapper.forward_incremental(
            snapshot=MagicMock(spec=BrowserSnapshot),
            previous_action_list=previous_actions(),
        )

    assert [action.id for action in result.actions] == ["B1"]
    assert pipe.forward_incremental.await_count == 1


@pytest.mark.asyncio
async def test_forward_raises_parsed_context_size_error_without_retrying() -> None:
    error = RuntimeError(
        "Please reduce the length of the messages or completions. Current length is 200 while limit is 100"
    )
    wrapper, pipe = make_wrapper(forward_side_effect=error, max_tries=3)

    with pytest.raises(ContextSizeTooLargeError, match="200.*100"):
        await wrapper.forward(snapshot=MagicMock(spec=BrowserSnapshot))

    assert pipe.forward.await_count == 1


@pytest.mark.asyncio
async def test_forward_preserves_engine_context_window_error_without_retrying() -> None:
    error = ContextWindowExceededError(provider="test/model", current_size=200, max_size=100)
    wrapper, pipe = make_wrapper(forward_side_effect=error, max_tries=3)

    with pytest.raises(ContextWindowExceededError) as exc_info:
        await wrapper.forward(snapshot=MagicMock(spec=BrowserSnapshot))

    assert exc_info.value is error
    assert pipe.forward.await_count == 1
