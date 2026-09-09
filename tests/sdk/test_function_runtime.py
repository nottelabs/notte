"""Runtime selection travels outside script variables and survives request conversion."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from notte_sdk.endpoints import workflows
from notte_sdk.endpoints.workflows import RemoteWorkflow, WorkflowsClient
from notte_sdk.types import RunFunctionRequest, StartFunctionRunRequest


@pytest.mark.parametrize("runtime", [None, "standard", "extended"])
def test_high_level_run_forwards_runtime(runtime):
    response = SimpleNamespace(status="closed", session_id=None)
    client = SimpleNamespace(run=Mock(return_value=response))
    function = SimpleNamespace(client=client, response=SimpleNamespace(function_id="function"))
    result = RemoteWorkflow.run(function, function_run_id="run", runtime=runtime, wait_seconds=960)
    assert result is response
    assert client.run.call_args.kwargs["runtime"] == runtime
    assert client.run.call_args.kwargs["variables"] == {"wait_seconds": 960}


@pytest.mark.parametrize("runtime", [None, "standard", "extended"])
@pytest.mark.parametrize("stream", [False, True])
def test_transport_preserves_selection(monkeypatch, runtime, stream):
    endpoint = SimpleNamespace(with_request=lambda request: request)
    client = SimpleNamespace(
        token="test",
        headers=lambda headers: headers,
        request_path=lambda endpoint: "https://example.com",
        _start_workflow_run_endpoint=lambda **kwargs: endpoint,
        WORKFLOW_RUN_TIMEOUT=900,
    )
    post = MagicMock(
        return_value=SimpleNamespace(
            json=lambda: {
                "function_id": "function",
                "function_run_id": "run",
                "status": "closed",
                "session_id": None,
                "result": {"ok": True},
            }
        )
    )
    post.return_value = MagicMock(json=post.return_value.json)
    post.return_value.__enter__.return_value = post.return_value
    post.return_value.iter_lines.return_value = [
        ("data: " + json.dumps({"type": "result", "message": json.dumps(post.return_value.json())})).encode()
    ]
    monkeypatch.setattr(workflows.requests, "post", post)
    WorkflowsClient.run(
        client, "run", function_id="function", variables={"wait_seconds": 960}, stream=stream, runtime=runtime
    )
    body = json.loads(post.call_args.kwargs["data"])
    assert body.get("runtime") == runtime
    assert body["variables"] == {"wait_seconds": 960}
    if runtime is None:
        assert "runtime" not in body
    else:
        assert body["runtime"] == runtime


def test_invalid_or_local_extended_rejected_before_creating_run():
    function = SimpleNamespace(client=SimpleNamespace(create_run=Mock()))
    with pytest.raises(ValueError, match="cloud"):
        RemoteWorkflow.run(function, local=True, runtime="extended")
    with pytest.raises(ValueError, match="standard.*extended"):
        RemoteWorkflow.run(function, runtime="invalid")
    function.client.create_run.assert_not_called()


def test_models_leave_runtime_unset():
    assert RunFunctionRequest(function_id="function", variables={}).runtime is None
    assert StartFunctionRunRequest(function_id="function").runtime is None


def test_script_inputs_can_use_reserved_sdk_option_names():
    response = SimpleNamespace(status="closed", session_id=None)
    client = SimpleNamespace(run=Mock(return_value=response))
    function = SimpleNamespace(client=client, response=SimpleNamespace(function_id="function"))
    RemoteWorkflow.run(
        function,
        function_run_id="run",
        runtime="extended",
        input_variables={"runtime": "python", "version": 3},
        wait_seconds=960,
    )
    assert client.run.call_args.kwargs["variables"] == {"runtime": "python", "version": 3, "wait_seconds": 960}
    assert client.run.call_args.kwargs["runtime"] == "extended"


def test_duplicate_inputs_rejected_before_creating_run():
    function = SimpleNamespace(client=SimpleNamespace(create_run=Mock()))
    with pytest.raises(ValueError, match="Duplicate input"):
        RemoteWorkflow.run(function, input_variables={"wait_seconds": 1}, wait_seconds=2)
    function.client.create_run.assert_not_called()


@pytest.mark.parametrize("raise_on_failure", [True, False])
def test_local_failure_persists_closed_but_reports_failure(monkeypatch, raise_on_failure):
    failure = RuntimeError("intentional test failure")
    runner = SimpleNamespace(run_script=Mock(side_effect=failure))
    monkeypatch.setattr(workflows, "SecureScriptRunner", lambda **kwargs: runner)
    client = SimpleNamespace(update_run=Mock())
    function = SimpleNamespace(
        client=client, function_id="function", root_client=object(), download=lambda **kwargs: "code"
    )
    if raise_on_failure:
        with pytest.raises(RuntimeError, match="intentional test failure"):
            RemoteWorkflow.run(function, function_run_id="run", local=True, raise_on_failure=True)
    else:
        result = RemoteWorkflow.run(function, function_run_id="run", local=True, raise_on_failure=False)
        assert result.status == "failed" and result.result == "intentional test failure"
    assert client.update_run.call_args.kwargs["status"] == "closed"
    assert client.update_run.call_args.kwargs["result"] == "intentional test failure"
