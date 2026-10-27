"""The OpenAPI contract check matches API properties to model fields through their aliases."""

import importlib.util
import json
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
    document = json.loads(json.dumps(document), object_pairs_hook=lambda pairs: dict(reversed(pairs)))
    assert contract.main() == 0
    assert contract.SNAPSHOT.read_bytes() == before
    document["components"]["schemas"]["Zebra"]["properties"]["a"]["minimum"] = 2
    assert contract.main() == 0
    assert contract.SNAPSHOT.read_bytes() != before


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
