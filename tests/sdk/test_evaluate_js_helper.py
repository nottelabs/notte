"""Remote `evaluate_js()`: the string on success, the typed raise on failure."""

import datetime as dt

import pytest
from notte_core.actions import EvaluateJsAction
from notte_core.browser.observation import ExecutionResult
from notte_core.data.space import DataSpace
from notte_core.errors.actions import ActionExecutionError, EvaluateJsNoDataError
from notte_core.errors.base import ErrorConfig

from tests.sdk.test_execute_raise_on_failure import over_the_wire, remote_session

CODE = "1 + 1"


def eval_result(*, success: bool, markdown: str | None = None, exception: Exception | None = None) -> ExecutionResult:
    now = dt.datetime.now(dt.timezone.utc)
    return ExecutionResult(
        action=EvaluateJsAction(code=CODE),
        success=success,
        message="ok" if success else "JavaScript evaluation failed: boom",
        data=DataSpace(markdown=markdown) if markdown is not None else None,
        exception=exception,
        started_at=now,
        ended_at=now,
    )


def test_evaluate_js_returns_the_string() -> None:
    session = remote_session(over_the_wire(eval_result(success=True, markdown="2")))

    assert session.evaluate_js(CODE) == "2"


def test_evaluate_js_failure_raises_the_typed_error() -> None:
    with ErrorConfig.message_mode("user"):
        exception = ActionExecutionError(action_id="evaluate_js", url="https://example.com", reason="boom")
    session = remote_session(over_the_wire(eval_result(success=False, exception=exception)))

    with pytest.raises(ActionExecutionError):
        _ = session.evaluate_js(CODE)


def test_evaluate_js_returns_the_envelope_when_not_raising() -> None:
    session = remote_session(over_the_wire(eval_result(success=False)))

    result = session.evaluate_js(CODE, raise_on_failure=False)

    assert isinstance(result, ExecutionResult)
    assert result.success is False


def test_evaluate_js_success_without_data_raises_instead_of_returning_none() -> None:
    """An API build that predates the eval-js fix can report success with no data."""
    session = remote_session(over_the_wire(eval_result(success=True)))

    with pytest.raises(EvaluateJsNoDataError, match="returned no data"):
        _ = session.evaluate_js(CODE)
