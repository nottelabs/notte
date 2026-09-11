from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from notte_sdk import NotteClient
from notte_sdk.types import CreateFunctionRunResponse, FunctionRunResponse


@pytest.mark.parametrize("local", [False, True])
def test_create_run_does_not_execute_or_fetch_function(local: bool) -> None:
    client = NotteClient(api_key="test-api-key", server_url="https://api.notte.cc")
    function = client.Function("function-123")
    created = CreateFunctionRunResponse(
        function_id="function-123", function_run_id="run-123", created_at=datetime.now(timezone.utc)
    )
    with (
        patch.object(client.functions, "create_run", return_value=created) as create,
        patch.object(client.functions, "get") as get,
        patch.object(client.functions, "run") as run,
    ):
        response = function.create_run(local=True) if local else function.create_run()

    assert response is created
    create.assert_called_once_with("function-123", local=local)
    get.assert_not_called()
    run.assert_not_called()
    assert function._function_run_id is None


def test_created_run_can_be_executed_without_creating_another() -> None:
    client = NotteClient(api_key="test-api-key", server_url="https://api.notte.cc")
    function = client.Function("function-123")
    created = CreateFunctionRunResponse(
        function_id="function-123", function_run_id="run-123", created_at=datetime.now(timezone.utc)
    )
    completed = FunctionRunResponse(
        function_id="function-123", function_run_id="run-123", session_id=None, status="closed", result={"ok": True}
    )
    with (
        patch.object(client.functions, "create_run", return_value=created) as create,
        patch.object(client.functions, "get") as get,
        patch.object(client.functions, "run", return_value=completed) as run,
    ):
        get.return_value.function_id = "function-123"
        response = function.create_run()
        result = function.run(function_run_id=response.function_run_id, url="https://example.com")

    assert result is completed
    create.assert_called_once_with("function-123", local=False)
    assert run.call_args.kwargs["function_run_id"] == "run-123"
    assert run.call_args.kwargs["variables"] == {"url": "https://example.com"}


def test_create_run_propagates_api_errors() -> None:
    client = NotteClient(api_key="test-api-key", server_url="https://api.notte.cc")
    function = client.Function("function-123")
    with patch.object(client.functions, "create_run", side_effect=ValueError("Function unavailable")):
        with pytest.raises(ValueError, match="Function unavailable"):
            function.create_run()
