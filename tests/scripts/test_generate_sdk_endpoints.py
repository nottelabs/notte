import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_sdk_endpoints", ROOT / "scripts/generate_sdk_endpoints.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


gen = _load()


@pytest.fixture
def spec() -> dict[str, Any]:
    return copy.deepcopy(json.loads((ROOT / "openapi/openapi.json").read_text()))


def test_the_committed_module_is_generated_from_the_snapshot(spec: dict[str, Any]) -> None:
    text, _ = gen.render(spec)
    assert (ROOT / "packages/notte-sdk/src/notte_sdk/_generated/endpoints.py").read_text() == text


def test_every_operation_the_sdk_calls_is_generated(spec: dict[str, Any]) -> None:
    _, blocks = gen.render(spec)
    assert gen.used_operations().keys() <= blocks.keys()


def test_a_query_model_with_a_parameter_the_api_lacks_fails(spec: dict[str, Any]) -> None:
    params = spec["paths"]["/personas/{persona_id}/emails"]["get"]["parameters"]
    spec["paths"]["/personas/{persona_id}/emails"]["get"]["parameters"] = [p for p in params if p["name"] != "limit"]
    with pytest.raises(gen.GenerationError, match="persona_emails_list: MessageReadRequest sends .*limit"):
        _ = gen.render(spec)


def test_an_override_whose_model_needs_missing_fields_fails(spec: dict[str, Any]) -> None:
    del spec["components"]["schemas"]["ProfileDeleteResponse"]["properties"]["success"]
    with pytest.raises(gen.GenerationError, match="profile_delete response: ExecutionResponse requires"):
        _ = gen.render(spec)


def test_a_live_api_only_fails_on_the_operations_the_sdk_calls(spec: dict[str, Any]) -> None:
    # An unused operation that no longer binds is left out instead of failing the release gate.
    del spec["components"]["schemas"]["ProfileDeleteResponse"]["properties"]["success"]
    _, blocks = gen.render(spec, strict=False)
    assert "profile_delete" not in blocks
    assert "persona_get" in blocks


def test_a_moved_path_changes_the_operation(spec: dict[str, Any]) -> None:
    _, before = gen.render(spec)
    spec["paths"]["/personas/{id}"] = spec["paths"].pop("/personas/{persona_id}")
    for operation in spec["paths"]["/personas/{id}"].values():
        for param in operation.get("parameters", []):
            if param["name"] == "persona_id":
                param["name"] = "id"
    _, after = gen.render(spec)
    assert before["persona_get"] != after["persona_get"]
    assert 'path=f"/personas/{_segment(id)}"' in after["persona_get"]
