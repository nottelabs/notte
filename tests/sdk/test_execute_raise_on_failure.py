"""Remote (SDK) counterpart of the local `raise_on_failure` gate in `NotteSession.execute`.

These tests exercise the *serialised* path: the action runs server side, the resulting
`ExecutionResult` is dumped to JSON and rebuilt by the client, and only then is the
raise gate evaluated.
"""

import datetime as dt
from typing import Any
from unittest.mock import MagicMock

import pytest
from notte_core.actions import EvaluateJsAction
from notte_core.browser.observation import ExecutionResult
from notte_core.errors.actions import ActionExecutionError
from notte_core.errors.base import ErrorConfig, ErrorMode, NotteBaseError
from notte_sdk.client import NotteClient
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.types import SessionResponse

TIMEOUT_MESSAGE: str = "JavaScript evaluation timed out after 45000ms"
ACTION: EvaluateJsAction = EvaluateJsAction(code="new Promise(() => {})")


def server_side_result(*, exception: Exception | None) -> ExecutionResult:
    """The `ExecutionResult` the API builds after a failed `evaluate_js` action."""
    now = dt.datetime.now(dt.timezone.utc)
    return ExecutionResult(
        action=ACTION,
        success=False,
        message=TIMEOUT_MESSAGE,
        data=None,
        exception=exception,
        started_at=now,
        ended_at=now,
    )


def over_the_wire(result: ExecutionResult) -> ExecutionResult:
    """Serialise server side and rebuild client side, like the real API round trip."""
    return ExecutionResult.model_validate_json(result.model_dump_json())


def remote_session(result: ExecutionResult, *, raise_on_failure: bool = True) -> RemoteSession:
    client = NotteClient(api_key="test-api-key")
    session = RemoteSession(_client=client.sessions, raise_on_failure=raise_on_failure)
    now = dt.datetime.now(dt.timezone.utc)
    session.response = SessionResponse(
        session_id="test-session-id",
        idle_timeout_minutes=1,
        created_at=now,
        last_accessed_at=now,
        status="active",
    )
    page_client: Any = MagicMock()
    page_client.execute = MagicMock(return_value=result)
    session.client.page = page_client
    return session


@pytest.mark.parametrize("server_error_mode", ["developer", "user"])
def test_remote_evaluate_js_failure_raises_with_the_actual_reason(server_error_mode: ErrorMode) -> None:
    """Whatever error mode the API serialises with, the caller sees the real reason."""
    with ErrorConfig.message_mode(server_error_mode):
        exception = ActionExecutionError(action_id=ACTION.type, url="https://example.com", reason=TIMEOUT_MESSAGE)
    session = remote_session(over_the_wire(server_side_result(exception=exception)))

    with pytest.raises(NotteBaseError) as exc_info:
        _ = session.execute(ACTION)

    assert TIMEOUT_MESSAGE in str(exc_info.value)


def test_remote_evaluate_js_failure_does_not_raise_when_disabled() -> None:
    """`raise_on_failure=False` still returns a result that says it failed."""
    with ErrorConfig.message_mode("developer"):
        exception = ActionExecutionError(action_id=ACTION.type, url="https://example.com", reason=TIMEOUT_MESSAGE)
    session = remote_session(over_the_wire(server_side_result(exception=exception)))

    result = session.execute(ACTION, raise_on_failure=False)

    assert result.success is False
    assert result.data is None
    assert result.message == TIMEOUT_MESSAGE


def test_remote_failure_without_exception_still_raises() -> None:
    """The API may report a failure without attaching an exception: still raise the reason."""
    session = remote_session(over_the_wire(server_side_result(exception=None)))

    with pytest.raises(NotteBaseError) as exc_info:
        _ = session.execute(ACTION)

    assert TIMEOUT_MESSAGE in str(exc_info.value)


def test_remote_failure_without_exception_is_quiet_when_disabled() -> None:
    session = remote_session(over_the_wire(server_side_result(exception=None)), raise_on_failure=False)

    result = session.execute(ACTION)

    assert result.success is False
    assert result.exception is None
    assert result.message == TIMEOUT_MESSAGE
