import json
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient
from notte_sdk.endpoints import workflows
from notte_sdk.endpoints.functions import NotteFunction
from notte_sdk.errors import NotteAPIError


@pytest.fixture
def function(tmp_path: Path) -> Generator[NotteFunction, None, None]:
    """Deploy an isolated function that needs no browser or external website."""
    _ = load_dotenv()
    client = NotteClient()
    source = tmp_path / "echo_function.py"
    source.write_text('def run(value: str) -> dict:\n    return {"echo": value}\n')
    fn = client.Function(path=str(source))
    try:
        yield fn
    finally:
        fn.delete()


@pytest.mark.parametrize("stream", [True, False])
def test_create_run_then_execute_and_retrieve(function: NotteFunction, stream: bool) -> None:
    """Exercise create_run -> run -> get_run through the live API, without mocks."""
    created = function.create_run()
    run_id = created.function_run_id
    try:
        assert created.function_id == function.function_id
        assert created.status == "created"
        assert run_id

        # Creation alone must leave the run unexecuted.
        before = function.get_run(run_id)
        assert before.function_run_id == run_id
        assert before.result is None
        assert before.local is False

        value = str(uuid4())
        result = function.run(function_run_id=run_id, stream=stream, value=value)
        assert result.function_run_id == run_id
        assert result.function_id == function.function_id
        assert result.status == "closed"
        assert result.result == {"echo": value}

        persisted = function.get_run(run_id)
        assert persisted.function_run_id == run_id
        assert persisted.status == "closed"
        assert persisted.variables == {"value": value}
        assert persisted.result is not None
        assert json.loads(persisted.result) == {"echo": value}
    finally:
        # Close an unstarted or interrupted run if an earlier assertion failed.
        if function.get_run(run_id).status == "active":
            function.stop_run(run_id)


def test_local_run_close_retries_an_attempt_that_already_landed(
    function: NotteFunction, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replay a local run's close as if its first attempt landed behind a gateway error.

    The live API accepts a repeated close with the same outcome, but rejects a
    different result or reopening the run with a 400 and keeps what it stored.
    """
    monkeypatch.setattr(workflows.time, "sleep", lambda _: None)
    client = function.client
    real_update_run = client.update_run
    sent: dict[str, Any] = {}

    def record(**kwargs: Any) -> Any:
        sent.update(kwargs)
        return real_update_run(**kwargs)

    monkeypatch.setattr(client, "update_run", record)
    run_id = function.create_run(local=True).function_run_id
    value = str(uuid4())
    assert function.run(function_run_id=run_id, local=True, value=value).status == "closed"
    original = function.get_run(run_id)
    assert original.status == "closed"

    def gateway_error() -> NotteAPIError:
        response = SimpleNamespace(status_code=502, json=lambda: {}, text="Bad gateway")
        return NotteAPIError(path="functions/runs", response=response)  # pyright: ignore[reportArgumentType]

    def close_behind_gateway_error(**payload: Any) -> None:
        attempts = iter([gateway_error()])

        def update_run(**kwargs: Any) -> Any:
            error = next(attempts, None)
            if error is not None:
                raise error
            return real_update_run(**kwargs)

        monkeypatch.setattr(client, "update_run", update_run)
        workflows._close_local_run(client, **payload)  # pyright: ignore[reportPrivateUsage]

    # The completion retry succeeds and preserves the original outcome.
    close_behind_gateway_error(**sent)
    replayed = function.get_run(run_id)
    assert replayed.status == "closed"
    assert replayed.result == sent["result"]
    assert replayed.updated_at == original.updated_at

    # A different outcome was never stored, so the API's rejection must surface.
    with pytest.raises(NotteAPIError) as exc:
        close_behind_gateway_error(**{**sent, "result": "a different result"})
    assert exc.value.status_code == 400
    unchanged = function.get_run(run_id)
    assert unchanged.status == "closed"
    assert unchanged.result == sent["result"]

    # Reopening is forbidden; the SDK must surface that rejection.
    with pytest.raises(NotteAPIError) as exc:
        close_behind_gateway_error(**{**sent, "status": "active"})
    assert exc.value.status_code == 400
    persisted = function.get_run(run_id)
    assert persisted.status == "closed"
    assert persisted.result == sent["result"]
    assert persisted.updated_at == original.updated_at
