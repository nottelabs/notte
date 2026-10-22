"""Runtime selection travels outside script variables and survives request conversion."""

import json
from functools import partial
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from notte_sdk import _transport as transport
from notte_sdk.endpoints.functions import FunctionsClient, NotteFunction
from notte_sdk.types import RunFunctionRequest, StartFunctionRunRequest


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
    client = SimpleNamespace(
        token="test",
        headers=lambda headers: headers,
        request_path=lambda endpoint: "https://example.com",
        _start_function_run_endpoint=lambda **kwargs: endpoint,
        FUNCTION_RUN_TIMEOUT=900,
    )
    # The real transport helpers, bound to the fake client.
    for name in ("request_once", "stream_lines", "_open_once"):
        setattr(client, name, partial(getattr(FunctionsClient, name), client))
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
    monkeypatch.setattr(transport.requests, "post", post)
    FunctionsClient.run_start(
        client, "run", function_id="function", variables={"wait_seconds": 960}, stream=stream, runtime=runtime
    )
    body = json.loads(post.call_args.kwargs["data"])
    assert body.get("runtime") == runtime
    assert body["variables"] == {"wait_seconds": 960}
    if runtime is None:
        assert "runtime" not in body
    else:
        assert body["runtime"] == runtime


@pytest.mark.parametrize("stream", [True, False])
def test_invalid_runtime_is_sent_and_api_422_is_typed(monkeypatch, stream):
    import requests
    from notte_sdk import NotteClient
    from notte_sdk.errors import NotteAPIError

    client = NotteClient(api_key="test-api-key", server_url="https://api.example.test")
    response = requests.Response()
    response.status_code = 422
    response._content = b'{"detail": "invalid runtime"}'
    post = MagicMock(return_value=response)
    monkeypatch.setattr(transport.requests, "post", post)
    function = SimpleNamespace(client=client.functions, response=SimpleNamespace(function_id="function"))
    with pytest.raises(NotteAPIError) as error:
        NotteFunction.run(function, function_run_id="run", runtime="invalid", stream=stream)
    assert error.value.status_code == 422
    assert json.loads(post.call_args.kwargs["data"])["runtime"] == "invalid"


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
