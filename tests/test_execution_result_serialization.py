"""ExecutionResult exception round-trips.

The legacy wire format serialized `exception` as `str(e)`, so the concrete error
type, the per-audience messages and the retry/notify flags were destroyed in
transit and every remote failure rehydrated as a bare `NotteBaseError`. The
additive `exception_detail` field carries the full error; these tests pin the
round-trip, the fallbacks, and compatibility with payloads from older servers.
"""

import json

import pytest
from notte_core.actions import ClickAction
from notte_core.browser.observation import ExecutionResult, SerializedError, TimedSpan
from notte_core.errors.actions import ActionExecutionError
from notte_core.errors.base import NotteBaseError


def _failed_result(exception: Exception) -> ExecutionResult:
    span = TimedSpan.start().close()
    return ExecutionResult(
        action=ClickAction(id="B1"),
        success=False,
        message="click failed",
        started_at=span.started_at,
        ended_at=span.ended_at,
        exception=exception,
    )


def test_notte_error_round_trips_with_type_messages_and_flags() -> None:
    original = ActionExecutionError(action_id="click", url="https://example.com", reason="element is disabled")
    dumped = _failed_result(original).model_dump_json()

    restored = ExecutionResult.model_validate_json(dumped)

    assert isinstance(restored.exception, ActionExecutionError)
    assert restored.exception.dev_message == original.dev_message
    assert restored.exception.user_message == original.user_message
    assert restored.exception.agent_message == original.agent_message
    assert restored.exception.should_retry_later is True
    assert restored.exception.should_notify_team is True
    assert "element is disabled" in restored.exception.dev_message


def test_legacy_payload_without_detail_keeps_old_behavior() -> None:
    original = ActionExecutionError(action_id="click", url="https://example.com", reason="element is disabled")
    payload = json.loads(_failed_result(original).model_dump_json())
    # An older server serializes only the stringified exception.
    del payload["exception_detail"]

    restored = ExecutionResult.model_validate(payload)

    assert type(restored.exception) is NotteBaseError
    assert restored.exception.dev_message == str(original)


def test_unknown_error_type_falls_back_to_base_class() -> None:
    detail = SerializedError(
        error_type="ServerOnlyError",
        dev_message="dev",
        user_message="user",
        agent_message="agent",
        should_retry_later=True,
    )
    payload = json.loads(_failed_result(ValueError("boom")).model_dump_json())
    payload["exception"] = "dev"
    payload["exception_detail"] = detail.model_dump()

    restored = ExecutionResult.model_validate(payload)

    assert type(restored.exception) is NotteBaseError
    assert restored.exception.dev_message == "dev"
    assert restored.exception.user_message == "user"
    assert restored.exception.should_retry_later is True


def test_first_party_error_outside_core_rehydrates_concrete_type() -> None:
    """Errors defined in notte-browser/notte-agent resolve without the caller importing them."""
    for error_type in ("InvalidLocatorRuntimeError", "MaxStepsReachedError", "PageLoadingError"):
        detail = SerializedError(
            error_type=error_type,
            dev_message="dev",
            user_message="user",
            agent_message="agent",
        )

        error = detail.to_exception()

        assert type(error).__name__ == error_type

    from notte_browser.errors import BrowserError

    # hierarchy matters: `except BrowserError` on the client must catch a
    # rehydrated PageLoadingError
    assert isinstance(
        SerializedError(
            error_type="PageLoadingError", dev_message="dev", user_message="user", agent_message="agent"
        ).to_exception(),
        BrowserError,
    )


def test_plain_exception_round_trips_messages() -> None:
    restored = ExecutionResult.model_validate_json(_failed_result(TimeoutError("boom")).model_dump_json())

    assert isinstance(restored.exception, NotteBaseError)
    assert restored.exception.dev_message == "boom"
    assert restored.exception.user_message == "boom"


def test_detail_only_payload_rehydrates_exception() -> None:
    payload = json.loads(
        _failed_result(ActionExecutionError(action_id="click", url="https://example.com")).model_dump_json()
    )
    # A future server may stop sending the lossy legacy field altogether.
    payload["exception"] = None

    restored = ExecutionResult.model_validate(payload)

    assert isinstance(restored.exception, ActionExecutionError)


def test_local_construction_populates_detail() -> None:
    result = _failed_result(ActionExecutionError(action_id="click", url="https://example.com", reason="nope"))

    assert result.exception_detail is not None
    assert result.exception_detail.error_type == "ActionExecutionError"
    assert "nope" in result.exception_detail.dev_message


def test_success_keeps_exception_invariant() -> None:
    span = TimedSpan.start().close()
    result = ExecutionResult(
        action=ClickAction(id="B1"),
        success=True,
        message="clicked",
        started_at=span.started_at,
        ended_at=span.ended_at,
    )
    assert result.exception is None
    assert result.exception_detail is None

    with pytest.raises(ValueError, match="Exception should be None"):
        ExecutionResult(
            action=ClickAction(id="B1"),
            success=True,
            message="clicked",
            started_at=span.started_at,
            ended_at=span.ended_at,
            exception=ValueError("boom"),
        )
