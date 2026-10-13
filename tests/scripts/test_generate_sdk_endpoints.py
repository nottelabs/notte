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


def test_resource_outputs_are_deterministic_and_fresh(spec: dict[str, Any]) -> None:
    outputs = gen.render_resources(spec)
    assert outputs == gen.render_resources(spec)
    for name, text in outputs.items():
        assert (ROOT / "packages/notte-sdk/src/notte_sdk/_generated" / name).read_text() == text
        assert "notte_core" not in text


@pytest.mark.parametrize("shape", ["binary", "inline", "optional_body", "header", "missing_operation"])
def test_unsupported_migrated_operations_fail_closed(spec: dict[str, Any], shape: str) -> None:
    op = spec["paths"]["/profiles/create"]["post"]
    if shape == "binary":
        op["responses"]["200"]["content"] = {"application/octet-stream": {"schema": {"type": "string"}}}
    elif shape == "inline":
        op["requestBody"]["content"]["application/json"]["schema"] = {"type": "object"}
    elif shape == "optional_body":
        op["requestBody"]["required"] = False
    elif shape == "header":
        op["parameters"].append({"in": "header", "name": "x-required", "required": True})
    else:
        del spec["paths"]["/profiles/create"]["post"]
    with pytest.raises(gen.GenerationError):
        _ = gen.render_resources(spec)


@pytest.mark.parametrize("change", ["query_default", "query_constraint", "response_schema", "path", "remove"])
def test_release_gate_includes_migrated_contracts(
    spec: dict[str, Any], monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    _, committed = gen.render(spec)
    monkeypatch.setattr(gen, "used_operations", lambda: {"profile_list": ["_generated/resources.py"]})
    monkeypatch.setattr(gen, "download", lambda _: spec)
    assert gen._check_against("https://example.test", committed) == 0
    if change == "query_default":
        params = spec["paths"]["/profiles"]["get"]["parameters"]
        next(p for p in params if p["name"] == "page_size")["schema"]["default"] = 99
    elif change == "query_constraint":
        params = spec["paths"]["/profiles"]["get"]["parameters"]
        next(p for p in params if p["name"] == "page_size")["schema"]["maximum"] = 101
    elif change == "response_schema":
        spec["components"]["schemas"]["ProfileResponse"]["properties"]["name"] = {"type": "integer"}
    elif change == "path":
        spec["paths"]["/new-profiles"] = spec["paths"].pop("/profiles")
    else:
        del spec["paths"]["/profiles"]["get"]
    assert gen._check_against("https://example.test", committed) == 1


def test_missing_resource_output_is_detected_without_rewriting(spec: dict[str, Any], tmp_path: Path) -> None:
    from scripts.generate_sdk_models import check_or_write

    outputs = gen.render_resources(spec)
    assert check_or_write(outputs, tmp_path, check=False)
    (tmp_path / "resources.py").unlink()
    (tmp_path / "operations.py").write_text("stale\n")
    assert not check_or_write(outputs, tmp_path, check=True)
    assert not (tmp_path / "resources.py").exists()
    assert (tmp_path / "operations.py").read_text() == "stale\n"


def test_migrated_release_gate_ignores_documentation_only_changes(
    spec: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, committed = gen.render(spec)
    monkeypatch.setattr(gen, "used_operations", lambda: {"profile_list": ["_generated/resources.py"]})
    monkeypatch.setattr(gen, "download", lambda _: spec)
    operation = spec["paths"]["/profiles"]["get"]
    operation["description"] = "Revised docs"
    operation["x-codeSamples"] = [{"lang": "Python", "source": "client.profiles.list()"}]
    operation["responses"]["200"]["content"]["application/json"]["example"] = {"$ref": "example data, not a schema"}
    schema = spec["components"]["schemas"]["ProfileResponse"]
    schema["title"] = "Updated title"
    schema["properties"]["name"]["description"] = "A better explanation"
    assert gen._check_against("https://example.test", committed) == 0


def test_migrated_contract_keeps_documentation_named_fields_and_literal_defaults(spec: dict[str, Any]) -> None:
    schema = spec["components"]["schemas"]["ProfileResponse"]
    schema["properties"]["description"] = {"type": "object", "default": {"title": "first", "$ref": "literal"}}
    before = gen.migrated_contracts(spec)
    schema["properties"]["description"]["default"]["title"] = "second"
    assert gen.migrated_contracts(spec) != before
    before = gen.migrated_contracts(spec)
    schema["properties"]["description"]["type"] = "string"
    assert gen.migrated_contracts(spec) != before
