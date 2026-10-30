"""Function wire contracts captured before the resource migration."""

import json
from typing import Any

import pytest
from notte_core import __version__
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import GetFunctionResponse, GetFunctionRunResponse, ListFunctionRunsResponse, ListFunctionsResponse

from tests.sdk.test_generated_endpoints import SERVER, fake
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client
STAMP = "2026-10-13T00:00:00Z"
FUNCTION = dict(
    function_id="fn", created_at=STAMP, updated_at=STAMP, latest_version="v1", versions=["v1"], status="active"
)
RUN = dict(function_id="fn", function_run_id="run", created_at=STAMP, updated_at=STAMP, status="active")
PAGE = dict(page=1, page_size=10, has_next=False, has_previous=False)


def test_function_wire_contract(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, {**FUNCTION, "url": "https://storage.example/code"})
    assert client.functions.download_url("fn").function_id == "fn"
    _ = client.functions.download_url("fn", version="v1")
    api.payload = FUNCTION
    assert client.functions.fork("fn").function_id == "fn"
    api.payload = {**PAGE, "items": [FUNCTION]}
    page = client.functions.list()
    assert isinstance(page, ListFunctionsResponse)
    assert isinstance(page.items[0], GetFunctionResponse)
    assert page.model_dump(mode="json")["has_next"] is False
    api.payload = {"status": "success", "message": "gone"}
    assert client.functions.delete("fn").status == "success"
    api.payload = {**RUN, "status": "created"}
    assert client.functions.create_run("fn").status == "created"
    api.payload = RUN
    run = client.functions.run_get_metadata("fn", "run")
    assert isinstance(run, GetFunctionRunResponse)
    assert run.logs == [] and run.variables == {}
    api.payload = {**RUN, "status": "updated"}
    assert client.functions.run_update_metadata("fn", "run", status="active").status == "updated"
    api.payload = {**RUN, "status": "stopped"}
    assert client.functions.run_stop("fn", "run").status == "stopped"
    api.payload = {**PAGE, "items": [RUN]}
    runs = client.functions.list_runs("fn")
    assert isinstance(runs, ListFunctionRunsResponse)
    assert runs.items[0].function_run_id == "run"
    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in api.calls] == [
        ("GET", "/functions/fn", {}),
        ("GET", "/functions/fn", {"version": "v1"}),
        ("POST", "/functions/fn/fork", {}),
        ("GET", "/functions/", {}),
        ("DELETE", "/functions/fn", {}),
        ("POST", "/functions/fn/runs/create", {}),
        ("GET", "/functions/fn/runs/run", {"payload_mode": "references"}),
        ("PATCH", "/functions/fn/runs/run", {}),
        ("DELETE", "/functions/fn/runs/run", {}),
        ("GET", "/functions/fn/runs/", {"only_active": "True"}),
    ]
    assert api.calls[2].data is None
    assert [json.loads(c.data) for c in api.calls if c.method in {"POST", "PATCH"} and c.data is not None] == [
        {},
        {"status": "active"},
    ]
    for call in api.calls:
        assert call.headers == {
            "Authorization": "Bearer test-api-key",  # pragma: allowlist secret
            "x-notte-sdk-version": __version__,
            "x-notte-request-origin": "sdk-python",
            **(
                {"Content-Type": "application/json"}
                if call.method in {"POST", "PATCH"} and call.data is not None
                else {}
            ),
        }


def test_create_run_sends_a_version_only_when_given(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, {**RUN, "status": "created"})
    _ = client.functions.create_run("fn", version="v1")
    _ = client.functions.create_run("fn")
    assert [(c.url.removeprefix(SERVER), json.loads(c.data)) for c in api.calls] == [
        ("/functions/fn/runs/create", {"version": "v1"}),
        ("/functions/fn/runs/create", {}),
    ]


@pytest.mark.parametrize(
    "name,args",
    [
        ("download_url", ("fn",)),
        ("fork", ("fn",)),
        ("delete", ("fn",)),
        ("list", ()),
        ("create_run", ("fn",)),
        ("run_get_metadata", ("fn", "run")),
        ("run_stop", ("fn", "run")),
        ("list_runs", ("fn",)),
    ],
)
@pytest.mark.parametrize("status", [404, 422])
def test_function_errors(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, name: str, args: tuple[str, ...], status: int
) -> None:
    api = fake(monkeypatch, {"detail": "function error"}, status)
    with pytest.raises(NotteAPIError) as error:
        getattr(client.functions, name)(*args)
    assert error.value.status_code == status
    assert len(api.calls) == 1


@pytest.mark.parametrize(
    "ids", [{"function_id": "canonical"}, {"workflow_id": "old"}, {"function_id": "canonical", "workflow_id": "old"}]
)
def test_function_response_alias_precedence(ids: dict[str, Any]) -> None:
    response = GetFunctionResponse.model_validate({**FUNCTION, **ids})
    assert response.function_id == ids.get("workflow_id", ids.get("function_id"))
    assert "workflow_id" not in response.model_dump()
    run = GetFunctionRunResponse.model_validate({**RUN, **ids, "workflow_run_id": "old-run"})
    assert run.function_run_id == "old-run"
    assert "workflow_run_id" not in run.model_dump()


@pytest.mark.parametrize(
    "name,args,data",
    [
        ("list", (), {"page": 0}),
        ("list_runs", ("fn",), {"page_size": 0}),
        ("run_update_metadata", ("fn", "run"), {"status": "invalid"}),
    ],
)
def test_invalid_function_requests_reach_api(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, name: str, args: tuple[str, ...], data: dict[str, Any]
) -> None:
    api = fake(monkeypatch, {"detail": "invalid input"}, 422)
    with pytest.raises(NotteAPIError) as error:
        getattr(client.functions, name)(*args, **data)
    assert error.value.status_code == 422
    assert len(api.calls) == 1
    if name == "run_update_metadata":
        supplied, expected = json.loads(api.calls[0].data), data
    else:
        # query parameters reach the wire as text
        supplied, expected = api.calls[0].params, {key: str(value) for key, value in data.items()}
    assert all(supplied[key] == value for key, value in expected.items())


def test_function_multipart_contract(client: NotteClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    path = tmp_path / "function.py"
    path.write_text("def run(): return 1\n")
    api = fake(monkeypatch, FUNCTION)
    _ = client.functions.create(path=str(path), name="fixture")
    _ = client.functions.update("fn", path=str(path), version="v1", restricted=False)
    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in api.calls] == [
        ("POST", "/functions/", {}),
        ("POST", "/functions/fn", {"restricted": "False", "version": "v1"}),
    ]
    # The local path is the uploaded file, not a form field.
    assert api.calls[0].data == {"name": "fixture"}
    assert api.calls[1].data == {}
    for call in api.calls:
        filename, content, _ = call.files["file"]
        assert (filename, content) == ("function.py", b"def run(): return 1\n")
    assert all("Content-Type" not in c.headers for c in api.calls)


def test_function_ids_are_encoded_as_one_segment(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, {**FUNCTION, "url": "https://storage.example/code"})
    _ = client.functions.download_url("a/b ?#%é")
    assert api.calls[0].url == SERVER + "/functions/a%2Fb%20%3F%23%25%C3%A9"


def test_function_response_types_are_generated() -> None:
    from notte_core import types as core
    from notte_sdk.types import GetFunctionWithLinkResponse

    assert GetFunctionResponse is core.GetFunctionResponse
    assert issubclass(GetFunctionWithLinkResponse, GetFunctionResponse)
    assert GetFunctionRunResponse is core.GetFunctionRunResponse


def test_function_runtime_metadata_survives_response_parsing(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake(
        monkeypatch,
        {**FUNCTION, "url": "https://storage.example/code", "sdk_generation": "v110", "upload_sdk_version": "1.10.0"},
    )
    function = client.functions.download_url("fn", function_run_id="run")
    assert function.sdk_generation == "v110"
    assert function.upload_sdk_version == "1.10.0"
    assert api.calls[0].params == {"function_run_id": "run"}
    api.payload = {**RUN, "artifact_sdk_generation": "v19", "sdk_generation": "v110"}
    run = client.functions.run_get_metadata("fn", "run")
    assert run.artifact_sdk_generation == "v19"
    assert run.sdk_generation == "v110"
    assert GetFunctionResponse.model_validate(FUNCTION).sdk_generation == "v19"
    assert GetFunctionRunResponse.model_validate(RUN).sdk_generation == "v19"


def test_function_update_accepts_nullable_logs_and_arbitrary_result() -> None:
    from notte_core.types import FunctionRunUpdateRequest

    update = FunctionRunUpdateRequest(status="active", logs=None, result={"ok": True})
    assert update.logs is None
    assert update.result == {"ok": True}
    assert FunctionRunUpdateRequest(status="closed", result=None).result is None


@pytest.mark.parametrize("shared", [True, False])
def test_function_sharing_metadata_round_trip(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, shared: bool
) -> None:
    api = fake(monkeypatch, {**FUNCTION, "shared": shared})
    response = client.functions.metadata_update("fn", shared=shared)
    assert response.shared is shared
    assert len(api.calls) == 1
    call = api.calls[0]
    assert (call.method, call.url) == ("PATCH", SERVER + "/functions/fn")
    assert json.loads(call.data) == {"shared": shared}


def test_function_metadata_preserves_omitted_and_null_sharing(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake(monkeypatch, {**FUNCTION, "shared": True})
    assert client.functions.metadata_update("fn", name="renamed").shared is True
    assert client.functions.metadata_update("fn", name="renamed", shared=None).shared is True
    assert [json.loads(call.data) for call in api.calls] == [{"name": "renamed"}, {"name": "renamed"}]
