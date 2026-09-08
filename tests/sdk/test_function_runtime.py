"""Runtime selection travels outside script variables and survives request conversion."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from notte_sdk.endpoints import workflows
from notte_sdk.endpoints.workflows import RemoteWorkflow, WorkflowsClient
from notte_sdk.types import RunFunctionRequest, StartFunctionRunRequest


@pytest.mark.parametrize("runtime", ["standard", "extended"])
def test_high_level_run_forwards_runtime(runtime):
    response = SimpleNamespace(status="closed", session_id=None)
    client = SimpleNamespace(run=Mock(return_value=response))
    function = SimpleNamespace(client=client, response=SimpleNamespace(function_id="function"))
    result = RemoteWorkflow.run(function, function_run_id="run", runtime=runtime, wait_seconds=960)
    assert result is response
    assert client.run.call_args.kwargs["runtime"] == runtime
    assert client.run.call_args.kwargs["variables"] == {"wait_seconds": 960}


@pytest.mark.parametrize("runtime", ["standard", "extended"])
def test_transport_preserves_selection(monkeypatch, runtime):
    endpoint = SimpleNamespace(with_request=lambda request: request)
    client = SimpleNamespace(
        token="test",
        headers=lambda headers: headers,
        request_path=lambda endpoint: "https://example.com",
        _start_workflow_run_endpoint=lambda **kwargs: endpoint,
        WORKFLOW_RUN_TIMEOUT=900,
    )
    post = Mock(
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
    monkeypatch.setattr(workflows.requests, "post", post)
    WorkflowsClient.run(
        client, "run", function_id="function", variables={"wait_seconds": 960}, stream=False, runtime=runtime
    )
    body = json.loads(post.call_args.kwargs["data"])
    assert body.get("runtime", "standard") == runtime
    assert body["variables"] == {"wait_seconds": 960}
    if runtime == "standard":
        assert "runtime" not in body  # Compatible with older APIs and Lambda images.


def test_invalid_or_local_extended_rejected_before_creating_run():
    function = SimpleNamespace(client=SimpleNamespace(create_run=Mock()))
    with pytest.raises(ValueError, match="cloud"):
        RemoteWorkflow.run(function, local=True, runtime="extended")
    with pytest.raises(ValueError, match="runtime must"):
        RemoteWorkflow.run(function, runtime="invalid")
    function.client.create_run.assert_not_called()


def test_models_default_to_standard():
    assert RunFunctionRequest(function_id="function", variables={}).runtime == "standard"
    assert StartFunctionRunRequest(function_id="function").runtime == "standard"
