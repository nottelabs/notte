"""A local run's final status update survives transient gateway and network errors."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from notte_sdk.endpoints import workflows
from notte_sdk.endpoints.workflows import RemoteWorkflow
from notte_sdk.errors import NotteAPIError


def api_error(status_code: int) -> NotteAPIError:
    def not_json():
        raise ValueError("not json")

    response = SimpleNamespace(status_code=status_code, json=not_json, text="<html>Bad gateway</html>")
    return NotteAPIError(path="functions/function/runs/run", response=response)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def sleeps(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(workflows.time, "sleep", sleep)
    return sleep


def run_locally(monkeypatch, client):
    runner = SimpleNamespace(run_script=Mock(return_value={"ok": True}))
    monkeypatch.setattr(workflows, "SecureScriptRunner", lambda **kwargs: runner)
    function = SimpleNamespace(
        client=client, function_id="function", root_client=object(), download=lambda **kwargs: "code"
    )
    return RemoteWorkflow.run(function, function_run_id="run", local=True)


@pytest.mark.parametrize("transient", [api_error(502), api_error(529), requests.ConnectionError("reset")])
def test_transient_close_failure_is_retried(monkeypatch, sleeps, transient):
    client = SimpleNamespace(update_run=Mock(side_effect=[transient, None]), get_run=Mock())
    result = run_locally(monkeypatch, client)
    assert result.status == "closed"
    assert client.update_run.call_count == 2
    assert client.update_run.call_args_list[0] == client.update_run.call_args_list[1]
    assert client.update_run.call_args.kwargs["status"] == "closed"
    sleeps.assert_called_once_with(workflows.LOCAL_RUN_CLOSE_RETRY_DELAYS[0])
    client.get_run.assert_not_called()


def test_retry_rejected_because_first_attempt_landed(monkeypatch, sleeps):
    client = SimpleNamespace(
        update_run=Mock(side_effect=[api_error(502), api_error(400)]),
        get_run=Mock(return_value=SimpleNamespace(status="closed")),
    )
    result = run_locally(monkeypatch, client)
    assert result.status == "closed"
    client.get_run.assert_called_once_with(function_id="function", run_id="run")


def test_retry_rejected_while_run_still_active_raises(monkeypatch, sleeps):
    client = SimpleNamespace(
        update_run=Mock(side_effect=[api_error(502), api_error(400)]),
        get_run=Mock(return_value=SimpleNamespace(status="active")),
    )
    with pytest.raises(NotteAPIError) as exc:
        _ = run_locally(monkeypatch, client)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("status_code", [400, 403, 404, 422])
def test_client_errors_are_not_retried(monkeypatch, sleeps, status_code):
    client = SimpleNamespace(update_run=Mock(side_effect=api_error(status_code)), get_run=Mock())
    with pytest.raises(NotteAPIError):
        _ = run_locally(monkeypatch, client)
    assert client.update_run.call_count == 1
    sleeps.assert_not_called()
    client.get_run.assert_not_called()


def test_gives_up_after_all_retries(monkeypatch, sleeps):
    attempts = len(workflows.LOCAL_RUN_CLOSE_RETRY_DELAYS) + 1
    client = SimpleNamespace(update_run=Mock(side_effect=[api_error(502)] * attempts), get_run=Mock())
    with pytest.raises(NotteAPIError) as exc:
        _ = run_locally(monkeypatch, client)
    assert exc.value.status_code == 502
    assert client.update_run.call_count == attempts
    assert [c.args[0] for c in sleeps.call_args_list] == list(workflows.LOCAL_RUN_CLOSE_RETRY_DELAYS)
