from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from notte_core.actions import CaptchaSolveAction, ClickAction
from notte_core.browser.observation import utc_now
from notte_sdk.client import NotteClient
from notte_sdk.endpoints.page import PageClient
from notte_sdk.types import CaptchaStatus, ExecutionResultResponse
from requests.exceptions import ChunkedEncodingError, Timeout


@pytest.fixture
def client(monkeypatch):
    page = PageClient(root_client=SimpleNamespace(captcha_timeout_seconds=180), api_key="test")
    clock = [0.0]
    monkeypatch.setattr("notte_sdk.endpoints.page.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("notte_sdk.endpoints.page.time.sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    return page, clock


def response(action, state=None, *, executed=False, success=False):
    return ExecutionResultResponse(
        action=action,
        success=success,
        message="result",
        started_at=utc_now(),
        ended_at=utc_now(),
        action_executed=executed,
        captcha=CaptchaStatus(captcha_id="solve", page_id="page", generation=0, state=state) if state else None,
    )


def test_long_solve_polls_same_id_with_short_requests(client):
    page, clock = client
    action = CaptchaSolveAction(captcha_type="recaptcha")
    page.request = MagicMock(
        side_effect=[response(action, "solving") for _ in range(75)] + [response(action, "solved", success=True)]
    )
    assert page.execute("session", action).success
    assert clock[0] == 75
    assert page.request.call_count == 76
    for call in page.request.call_args_list[1:]:
        assert call.args[0].params.captcha_id == "solve"
        assert call.kwargs["timeout"] <= 10


def test_blocked_action_runs_only_after_solve(client):
    page, _ = client
    action = ClickAction(selector="#submit")
    page.request = MagicMock(
        side_effect=[
            response(action, "solving"),
            response(CaptchaSolveAction(), "solved", success=True),
            response(action, success=True),
        ]
    )
    assert page.execute("session", action).success
    calls = page.request.call_args_list
    assert [call.args[0].request.type for call in calls] == ["click", "captcha_solve", "click"]
    assert calls[2].args[0].params.target_page_id == "page"
    assert calls[2].args[0].params.target_generation == 0
    assert calls[2].args[0].params.captcha_id is None


def test_action_that_triggered_captcha_is_not_replayed(client):
    page, _ = client
    action = ClickAction(selector="#submit")
    initial = response(action, "solving", executed=True, success=True)
    page.request = MagicMock(side_effect=[initial, response(CaptchaSolveAction(), "solved", success=True)])
    result = page.execute("session", action)
    assert result.success and result.action == action
    assert result.action_executed is True
    assert page.request.call_count == 2
    assert result.captcha.state == "solved"


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_terminal_failure_keeps_execution_state(client, state):
    page, _ = client
    action = ClickAction(selector="#submit")
    page.request = MagicMock(
        side_effect=[response(action, "solving", executed=True, success=True), response(CaptchaSolveAction(), state)]
    )
    result = page.execute("session", action)
    assert not result.success
    assert result.action_executed is True
    assert result.exception is not None
    assert result.code == f"captcha_{state}"


def test_total_deadline_is_not_reset_by_polls(client):
    page, clock = client
    page.root_client.captcha_timeout_seconds = 3
    action = CaptchaSolveAction()
    page.request = MagicMock(return_value=response(action, "solving"))
    result = page.execute("session", action)
    assert not result.success and result.code == "captcha_timeout"
    assert clock[0] == 3
    assert page.request.call_count == 3


@pytest.mark.parametrize("error", [Timeout, ChunkedEncodingError])
def test_ordinary_transport_timeout_never_retries(client, error):
    page, _ = client
    page.request = MagicMock(side_effect=error())
    with pytest.raises(error):
        page.execute("session", ClickAction(selector="#submit"))
    assert page.request.call_count == 1


@pytest.mark.parametrize("error", [Timeout, ChunkedEncodingError])
def test_poll_transport_timeout_resumes_same_solve(client, error):
    page, _ = client
    action = CaptchaSolveAction()
    page.request = MagicMock(
        side_effect=[response(action, "solving"), error(), response(action, "solved", success=True)]
    )
    assert page.execute("session", action).success
    assert page.request.call_args.args[0].params.captcha_id == "solve"


@pytest.mark.parametrize("budget", [0, -1, float("inf"), float("nan")])
def test_invalid_wait_budget(budget):
    with pytest.raises(ValueError, match="captcha_timeout_seconds"):
        NotteClient(api_key="test", captcha_timeout_seconds=budget)  # pragma: allowlist secret


def test_missing_poll_status_cannot_report_action_success(client):
    page, _ = client
    action = ClickAction(selector="#submit")
    page.request = MagicMock(side_effect=[response(action, "solving"), response(CaptchaSolveAction(), success=True)])
    result = page.execute("session", action)
    assert not result.success and result.code == "captcha_protocol_error"
    assert result.action == action
    assert page.request.call_count == 2


@pytest.mark.parametrize("error", [Timeout, ChunkedEncodingError])
def test_initial_solve_transport_failure_is_not_retried(client, error):
    page, _ = client
    page.request = MagicMock(side_effect=error("initial response lost"))
    with pytest.raises(error):
        page.execute("session", CaptchaSolveAction())
    assert page.request.call_count == 1


@pytest.mark.parametrize("success", [False, True])
def test_navigation_preserves_executed_result_without_replay(client, success):
    page, _ = client
    action = ClickAction(selector="#submit")
    original = response(action, "solving", executed=True, success=success)
    cancelled = response(CaptchaSolveAction(), "cancelled")
    cancelled.captcha.cancel_reason = "navigation"
    page.request = MagicMock(side_effect=[original, cancelled])
    result = page.execute("session", action)
    assert result.success is success
    assert result.message == original.message
    assert result.action == action
    assert result.action_executed is True
    assert result.captcha.state == "cancelled"
    assert page.request.call_count == 2


@pytest.mark.parametrize("explicit", [False, True])
def test_navigation_does_not_resume_blocked_action_or_succeed_explicit_solve(client, explicit):
    page, _ = client
    action = CaptchaSolveAction() if explicit else ClickAction(selector="#submit")
    cancelled = response(CaptchaSolveAction(), "cancelled")
    cancelled.captcha.cancel_reason = "navigation"
    page.request = MagicMock(side_effect=[response(action, "solving"), cancelled])
    result = page.execute("session", action)
    assert not result.success and result.code == "captcha_cancelled"
    assert page.request.call_count == 2
