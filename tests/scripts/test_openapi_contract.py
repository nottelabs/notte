"""The OpenAPI contract check matches API properties to model fields through their aliases."""

import copy
import importlib.util
import io
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Annotated, Any, TypeAlias

import pytest
from pydantic import AliasChoices, BaseModel, Field

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("openapi_contract", ROOT / "scripts/openapi_contract.py")
assert spec and spec.loader
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def test_fetch_is_an_ordering_only_noop_but_keeps_real_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document = json.loads((ROOT / "tests/data/openapi-order/input.json").read_text())
    monkeypatch.setattr(contract, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(contract, "SNAPSHOT", tmp_path / "openapi.json")
    monkeypatch.setattr(contract.sys, "argv", ["openapi_contract.py", "--fetch"])
    monkeypatch.setattr(contract, "download", lambda _: document)
    monkeypatch.setattr(contract, "api_version", lambda: "1")
    assert contract.main() == 0
    before = contract.SNAPSHOT.read_bytes()
    assert list(json.loads(before)["components"]["schemas"]["Zebra"]["properties"]) == ["z", "a"]
    document = json.loads(json.dumps(document), object_pairs_hook=lambda pairs: dict(reversed(pairs)))
    assert contract.main() == 0
    assert contract.SNAPSHOT.read_bytes() == before
    document["components"]["schemas"]["Zebra"]["properties"]["a"]["minimum"] = 2
    assert contract.main() == 0
    assert contract.SNAPSHOT.read_bytes() != before
    assert list(json.loads(contract.SNAPSHOT.read_text())["components"]["schemas"]["Zebra"]["properties"]) == ["a", "z"]


@pytest.mark.parametrize("change", ["add", "remove", "type", "default", "required", "constraint", "tuple", "examples"])
def test_fetch_keeps_real_contract_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str) -> None:
    document = json.loads((ROOT / "tests/data/openapi-order/input.json").read_text())
    snapshot = tmp_path / "openapi.json"
    original = json.dumps(document, indent=4) + "\n"
    snapshot.write_text(original)
    updated = copy.deepcopy(document)
    model = updated["components"]["schemas"]["Zebra"]
    if change == "add":
        model["properties"]["new_field"] = {"type": "boolean"}
    elif change == "remove":
        del model["properties"]["z"]
    elif change == "type":
        model["properties"]["a"]["type"] = "number"
    elif change == "default":
        model["properties"]["z"]["default"] = "changed"
    elif change == "required":
        model["required"].pop()
    elif change == "constraint":
        model["properties"]["a"]["minimum"] = 2
    elif change == "tuple":
        updated["components"]["schemas"]["Alpha"]["prefixItems"].reverse()
    else:
        updated["components"]["schemas"]["Alpha"]["examples"].reverse()
    monkeypatch.setattr(contract, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(contract, "SNAPSHOT", snapshot)
    monkeypatch.setattr(contract.sys, "argv", ["openapi_contract.py", "--fetch"])
    monkeypatch.setattr(contract, "download", lambda _: updated)
    monkeypatch.setattr(contract, "api_version", lambda: "1")
    assert contract.main() == 0
    assert json.loads(snapshot.read_text()) == updated
    assert snapshot.read_text() != original


Json: TypeAlias = "str | dict[str, Json]"


def _versioned_schema(version: str) -> dict[str, Json]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Notte API", "version": version},
        "components": {
            "schemas": {
                "HealthResponse": {"properties": {"version": {"type": "string", "default": version}}},
                "FunctionVersionOriginInfo": {"properties": {"version": {"type": "string"}}},
                "RunFunctionRequest": {"properties": {"version": {"type": "string", "default": "latest"}}},
                "FunctionRollbackRequest": {"properties": {"version": {"type": "string", "default": "1.10.15"}}},
            }
        },
    }


def test_fetch_writes_the_version_the_api_reports_with_this_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The published schema comes from the API's pinned notte (1.10.15); the round trip installs
    # this workspace (1.10.16.dev0), and the API then reports 1.10.16.
    snapshot = tmp_path / "openapi.json"
    snapshot.write_text(json.dumps(_versioned_schema("1.10.15"), indent=2) + "\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "notte"\nversion = "1.10.16.dev0"\n')
    monkeypatch.setattr(contract, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(contract, "SNAPSHOT", snapshot)
    monkeypatch.setattr(contract, "PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(contract.sys, "argv", ["openapi_contract.py", "--fetch"])
    monkeypatch.setattr(contract, "download", lambda _: _versioned_schema("1.10.15"))
    assert contract.main() == 0
    # Only the API's own version moves: other `version` properties keep their defaults.
    written = json.loads(snapshot.read_text())
    schemas = written["components"]["schemas"]
    assert written["info"]["version"] == "1.10.16"
    assert schemas["HealthResponse"]["properties"]["version"]["default"] == "1.10.16"
    assert schemas["FunctionRollbackRequest"]["properties"]["version"]["default"] == "1.10.15"
    assert schemas["RunFunctionRequest"]["properties"]["version"]["default"] == "latest"
    assert "default" not in schemas["FunctionVersionOriginInfo"]["properties"]["version"]
    before = snapshot.read_bytes()
    assert contract.main() == 0
    assert snapshot.read_bytes() == before


def test_stamp_version_moves_only_the_api_version_in_the_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The release workflow's development bump stamps the snapshot without fetching it.
    snapshot = tmp_path / "openapi.json"
    snapshot.write_text(json.dumps(_versioned_schema("1.10.18"), indent=2) + "\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "notte"\nversion = "1.10.19.dev0"\n')
    monkeypatch.setattr(contract, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(contract, "SNAPSHOT", snapshot)
    monkeypatch.setattr(contract, "PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(contract.sys, "argv", ["openapi_contract.py", "--stamp-version"])
    monkeypatch.setattr(contract, "download", lambda _: pytest.fail("--stamp-version must not fetch"))
    assert contract.main() == 0
    expected = _versioned_schema("1.10.18")
    expected["info"]["version"] = "1.10.19"
    expected["components"]["schemas"]["HealthResponse"]["properties"]["version"]["default"] = "1.10.19"
    assert snapshot.read_text() == json.dumps(expected, indent=2) + "\n"


def test_the_committed_snapshot_reports_this_workspace_version() -> None:
    # The schema round trip installs this workspace into the API, which then reports its version.
    # A version bump that leaves the snapshot behind fails there; run `openapi_contract.py --stamp-version`.
    snapshot = json.loads((ROOT / "openapi/openapi.json").read_text())
    version = contract.api_version()
    assert snapshot["info"]["version"] == version
    assert snapshot["components"]["schemas"]["HealthResponse"]["properties"]["version"]["default"] == version


@pytest.mark.parametrize(
    ("workspace", "reported"),
    [("1.10.16.dev0", "1.10.16"), ("1.10.16.dev", "1.10.16"), ("1.9.1.dev12", "1.9.1"), ("1.10.16", "1.10.16")],
)
def test_the_api_version_drops_only_the_dev_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workspace: str, reported: str
) -> None:
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "notte"\nversion = "{workspace}"\n')
    monkeypatch.setattr(contract, "PYPROJECT", tmp_path / "pyproject.toml")
    assert contract.api_version() == reported


class RunRequest(BaseModel):
    function_id: Annotated[str, Field(validation_alias=AliasChoices("workflow_id", "function_id"))]
    variables: dict[str, Any] = {}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"properties": properties, "required": required}


def test_a_property_read_through_a_validation_alias_is_not_drift() -> None:
    schema = _schema({"workflow_id": {"type": "string"}, "variables": {"type": "object"}}, ["workflow_id"])
    assert contract._model_drift("RunRequest", RunRequest, schema) == []  # pyright: ignore[reportPrivateUsage]


def test_both_names_served_by_the_api_map_to_one_field() -> None:
    schema = _schema(
        {"function_id": {"type": "string"}, "workflow_id": {"type": "string"}, "variables": {"type": "object"}},
        ["function_id", "workflow_id"],
    )
    assert contract._model_drift("RunRequest", RunRequest, schema) == []  # pyright: ignore[reportPrivateUsage]


def test_requiredness_is_compared_through_the_alias() -> None:
    schema = _schema({"workflow_id": {"type": "string"}, "variables": {"type": "object"}}, [])
    assert contract._model_drift("RunRequest", RunRequest, schema) == [  # pyright: ignore[reportPrivateUsage]
        "RunRequest: workflow_id (read as function_id) required api=False sdk=True"
    ]


@pytest.mark.parametrize(
    "prop",
    [
        {"anyOf": [{"type": "string"}, {"type": "null"}]},
        {"type": ["string", "null"]},
    ],
    ids=["any-of", "type-list"],
)
def test_both_ways_of_writing_a_nullable_field_are_nullable(prop: dict[str, Any]) -> None:
    assert contract._nullable(prop)  # pyright: ignore[reportPrivateUsage]


def test_a_type_list_without_null_is_not_nullable() -> None:
    assert not contract._nullable({"type": ["string", "integer"]})  # pyright: ignore[reportPrivateUsage]


def test_unknown_names_are_still_drift() -> None:
    schema = _schema({"pipeline_id": {"type": "string"}, "variables": {"type": "object"}}, ["pipeline_id"])
    assert contract._model_drift("RunRequest", RunRequest, schema) == [  # pyright: ignore[reportPrivateUsage]
        "RunRequest: api-only field pipeline_id (required)",
        "RunRequest: sdk-only field function_id",
    ]


@pytest.mark.parametrize(
    "url,authorized",
    [
        ("https://us-staging.notte.cc", True),
        ("https://us-staging.notte.cc/", True),
        ("https://us-staging.notte.cc///", True),
        ("https://preview-20-dev-test.notte.cc", True),
        ("https://api.notte.cc", True),
        ("http://us-staging.notte.cc", False),
        ("https://us-staging.notte.cc.evil.test", False),
        ("https://example.com", False),
        ("https://us-staging.notte.cc@evil.test/", False),
        ("https://us-staging.notte.cc/custom/", False),
        ("https://preview-21-dev-test.notte.cc", False),
    ],
)
@pytest.mark.parametrize("key", [None, "", "fixture-key"])
def test_schema_key_is_scoped_to_api_origins(monkeypatch, url: str, authorized: bool, key: str | None) -> None:
    if key is None:
        monkeypatch.delenv("NOTTE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("NOTTE_API_KEY", key)

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == f"{url.rstrip('/')}/openapi.json"
            assert request.get_header("Authorization") == ("Bearer fixture-key" if authorized and key else None)
            assert timeout == 120
            return io.StringIO('{"openapi":"3.1.0"}')

    monkeypatch.setattr(contract.urllib.request, "build_opener", lambda *handlers: Opener())
    assert contract.download(url) == {"openapi": "3.1.0"}


def test_schema_download_refuses_redirects(monkeypatch) -> None:
    monkeypatch.setenv("NOTTE_API_KEY", "fixture-key")
    paths: list[str] = []

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/elsewhere")
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            contract.download(f"http://127.0.0.1:{server.server_port}")
        assert error.value.code == 302
        assert paths == ["/openapi.json"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
