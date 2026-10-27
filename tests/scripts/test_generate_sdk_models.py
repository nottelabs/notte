"""Generation must be complete, reproducible, and fail closed on stale artifacts."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("generate_sdk_models", ROOT / "scripts/generate_sdk_models.py")
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_regeneration_matches_committed_files() -> None:
    # render uses a fresh temporary directory every time: paths/timestamps must not leak.
    assert gen.check_or_write(gen.render(), gen.OUTPUT, check=True)


def test_object_order_and_formatting_do_not_change_generated_models(tmp_path: Path) -> None:
    spec = json.loads(gen.SNAPSHOT.read_text(), object_pairs_hook=lambda pairs: dict(reversed(pairs)))
    snapshot = tmp_path / "reordered.json"
    snapshot.write_text(json.dumps(spec))
    assert gen.check_or_write(gen.render(snapshot), gen.OUTPUT, check=True)


@pytest.mark.parametrize("change", ["add", "remove", "type", "default", "required", "constraint"])
def test_real_contract_changes_still_change_generated_output(tmp_path: Path, change: str) -> None:
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Probe", "version": "1"},
        "paths": {},
        "components": {
            "schemas": {
                "Probe": {
                    "type": "object",
                    "required": ["a"],
                    "properties": {"a": {"type": "integer", "minimum": 1}, "z": {"type": "string", "default": "z"}},
                }
            }
        },
    }
    snapshot = tmp_path / "probe.json"
    snapshot.write_text(json.dumps(spec))
    baseline = gen.render(snapshot)
    model = spec["components"]["schemas"]["Probe"]
    if change == "add":
        model["properties"]["new_field"] = {"type": "boolean"}
    elif change == "remove":
        del model["properties"]["z"]
    elif change == "type":
        model["properties"]["a"]["type"] = "number"
    elif change == "default":
        model["properties"]["z"]["default"] = "changed"
    elif change == "required":
        model["required"] = []
    else:
        model["properties"]["a"]["minimum"] = 2
    snapshot.write_text(json.dumps(spec))
    changed = gen.render(snapshot)
    assert changed["models.py"] != baseline["models.py"]
    assert gen.check_or_write(baseline, tmp_path / "generated", check=False)
    assert not gen.check_or_write(changed, tmp_path / "generated", check=True)
    assert gen.render(snapshot) == changed


def test_spec_change_changes_models_and_index(tmp_path: Path) -> None:
    spec = json.loads(gen.SNAPSHOT.read_text())
    spec["components"]["schemas"]["CodegenCoverageProbe"] = {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "integer", "minimum": 1}},
    }
    snapshot = tmp_path / "changed.json"
    snapshot.write_text(json.dumps(spec))
    generated = gen.render(snapshot)
    assert "class CodegenCoverageProbe(BaseModel)" in generated["models.py"]
    assert '"#/components/schemas/CodegenCoverageProbe": "CodegenCoverageProbe"' in generated["schema_index.json"]
    assert generated["models.py"] != (gen.OUTPUT / "models.py").read_text()


def test_check_detects_missing_and_stale_files_without_writing(tmp_path: Path) -> None:
    expected = {"models.py": "expected\n", "schema_index.json": "{}\n"}
    assert not gen.check_or_write(expected, tmp_path, check=True)
    assert list(tmp_path.iterdir()) == []
    assert gen.check_or_write(expected, tmp_path, check=False)
    (tmp_path / "models.py").write_text("stale\n")
    assert not gen.check_or_write(expected, tmp_path, check=True)
    assert (tmp_path / "models.py").read_text() == "stale\n"


def test_unpinned_generator_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen, "version", lambda _: "0.0.0")
    with pytest.raises(ValueError, match="datamodel-code-generator==0.86.0 required"):
        gen.render()
