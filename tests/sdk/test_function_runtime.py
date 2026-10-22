"""Runtime selection travels outside script variables and survives request conversion."""

import json
from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from notte_sdk.endpoints.functions import FunctionsClient, NotteFunction
from notte_sdk.types import RunFunctionRequest, StartFunctionRunRequest

from tests.sdk.test_generated_endpoints import FakeSession, fake


@pytest.mark.parametrize("runtime", [None, "standard", "extended"])
def test_high_level_run_forwards_runtime(runtime):
    response = SimpleNamespace(status="closed", session_id=None)
    client = SimpleNamespace(run_start=Mock(return_value=response))
    function = SimpleNamespace(client=client, response=SimpleNamespace(function_id="function"))
    result = NotteFunction.run(function, function_run_id="run", runtime=runtime, wait_seconds=960)
    assert result is response
    assert client.run_start.call_args.kwargs["runtime"] == runtime
    assert client.run_start.call_args.kwargs["variables"] == {"wait_seconds": 960}


@pytest.mark.parametrize("runtime", [None, "standard", "extended"])
@pytest.mark.parametrize("stream", [False, True])
def test_transport_preserves_selection(monkeypatch, runtime, stream):
    endpoint = SimpleNamespace(with_request=lambda request: SimpleNamespace(request=request))
    run = {
        "function_id": "function",
        "function_run_id": "run",
        "status": "closed",
        "session_id": None,
        "result": {"ok": True},
    }
    api = FakeSession(
        ("data: " + json.dumps({"type": "result", "message": json.dumps(run)})).encode() if stream else run
    )
    client = SimpleNamespace(
        token="test",
        headers=lambda headers: headers,
        request_path=lambda endpoint: "https://example.com",
        _start_function_run_endpoint=lambda **kwargs: endpoint,
        FUNCTION_RUN_TIMEOUT=900,
        http=api.client,
    )
    # The real transport helpers, bound to the fake client.
    for name in ("_request_once", "_stream_lines", "_once_request"):
        setattr(client, name, partial(getattr(FunctionsClient, name), client))
    FunctionsClient.run_start(
        client, "run", function_id="function", variables={"wait_seconds": 960}, stream=stream, runtime=runtime
    )
    assert [(call.method, call.url) for call in api.calls] == [("POST", "https://example.com")]
    body = json.loads(api.calls[0].data)
    assert body.get("runtime") == runtime
    assert body["variables"] == {"wait_seconds": 960}
    if runtime is None:
        assert "runtime" not in body
    else:
        assert body["runtime"] == runtime


@pytest.mark.parametrize("stream", [True, False])
def test_invalid_runtime_is_sent_and_api_422_is_typed(monkeypatch, stream):
    from notte_sdk import NotteClient
    from notte_sdk.errors import NotteAPIError

    client = NotteClient(api_key="test-api-key", server_url="https://api.example.test")
    api = fake(monkeypatch, {"detail": "invalid runtime"}, 422)
    function = SimpleNamespace(client=client.functions, response=SimpleNamespace(function_id="function"))
    with pytest.raises(NotteAPIError) as error:
        NotteFunction.run(function, function_run_id="run", runtime="invalid", stream=stream)
    assert error.value.status_code == 422
    assert error.value.error == {"detail": "invalid runtime"}
    assert json.loads(api.calls[0].data)["runtime"] == "invalid"
    assert api.bodies[0].closed


def test_models_leave_runtime_unset():
    assert RunFunctionRequest(function_id="function", variables={}).runtime is None
    assert StartFunctionRunRequest(function_id="function").runtime is None


def test_script_inputs_can_use_reserved_sdk_option_names():
    response = SimpleNamespace(status="closed", session_id=None)
    client = SimpleNamespace(run_start=Mock(return_value=response))
    function = SimpleNamespace(client=client, response=SimpleNamespace(function_id="function"))
    NotteFunction.run(
        function,
        function_run_id="run",
        runtime="extended",
        input_variables={"runtime": "python", "version": 3},
        wait_seconds=960,
    )
    assert client.run_start.call_args.kwargs["variables"] == {"runtime": "python", "version": 3, "wait_seconds": 960}
    assert client.run_start.call_args.kwargs["runtime"] == "extended"


def test_duplicate_inputs_rejected_before_creating_run():
    function = SimpleNamespace(client=SimpleNamespace(create_run=Mock()))
    with pytest.raises(ValueError, match="Duplicate input"):
        NotteFunction.run(function, input_variables={"wait_seconds": 1}, wait_seconds=2)
    function.client.create_run.assert_not_called()
