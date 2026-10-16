import json
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient
from notte_sdk.endpoints.functions import NotteFunction


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
