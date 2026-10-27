"""The OpenAPI contract check matches API properties to model fields through their aliases."""

import copy
import importlib.util
import io
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Annotated, Any

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
    assert contract.main() == 0
    assert json.loads(snapshot.read_text()) == updated
    assert snapshot.read_text() != original


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
        ("https://preview-20-dev-test.notte.cc", True),
        ("https://api.notte.cc", True),
        ("http://us-staging.notte.cc", False),
        ("https://us-staging.notte.cc.evil.test", False),
        ("https://example.com", False),
        ("https://preview-21-dev-test.notte.cc", False),
    ],
)
def test_schema_key_is_scoped_to_api_origins(monkeypatch, url: str, authorized: bool) -> None:
    monkeypatch.setenv("NOTTE_API_KEY", "fixture-key")

    class Opener:
        def open(self, request, timeout):
            assert request.get_header("Authorization") == ("Bearer fixture-key" if authorized else None)
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
