"""Reference freshness has one owner for each selected change."""

import json
from pathlib import Path

import pytest
import yaml

from scripts import ci_scope

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        "node-sdk/package.json",
        "node-sdk/src/resources.gen.ts",
        "node-sdk/src/lib/client/types.gen.ts",
        "node-sdk/src/index.ts",
        "node-sdk/scripts/generate-reference.mjs",
        "docs/src/typescript-sdk-reference/index.mdx",
        "docs/src/snippets/sessions/index.mdx",
        "docs/src/testers/sessions/index.ts",
        "docs/src/docs.json",
        ".github/workflows/typescript-sdk-reference.yml",
    ],
)
def test_one_freshness_check_per_reference_input(path: str) -> None:
    reference = yaml.safe_load((ROOT / ".github/workflows/typescript-sdk-reference.yml").read_text())
    job = reference["jobs"]["generated-reference"]
    assert job["strategy"]["matrix"]["node"] == [22, 24]
    steps = job["steps"]
    assert next(step for step in steps if step.get("run") == "npm run docs:test").get("if") is None
    check = next(step for step in steps if step.get("run") == "npm run docs:check")
    assert check["if"] == "matrix.node == 22 && !fromJSON(steps.scope.outputs.scope).node_generated"
    assert next(step for step in steps if "checkout@" in step.get("uses", ""))["with"]["fetch-depth"] == 0
    assert next(step for step in steps if step.get("id") == "scope")["uses"] == "./.github/actions/ci-scope"
    events = reference[True]
    assert events["push"]["paths"] == events["pull_request"]["paths"]
    assert "node-sdk/**" in events["push"]["paths"]
    generated_selected = "node_generated" in ci_scope.scopes_for_path(path)
    reference_checks = sum(node == 22 and not generated_selected for node in job["strategy"]["matrix"]["node"])
    assert reference_checks + int(generated_selected) == 1


def test_generation_freshness_keeps_required_gate_owner() -> None:
    node = yaml.safe_load((ROOT / ".github/workflows/node-sdk-ci.yml").read_text())
    generated = node["jobs"]["generated"]
    assert generated["if"] == "fromJSON(needs.changes.outputs.scope).node_generated"
    assert any(step.get("run") == "npm run check:generated" for step in generated["steps"])
    package = json.loads((ROOT / "node-sdk/package.json").read_text())
    assert "npm run docs:check" in package["scripts"]["check:generated"]
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert "node" in ci["jobs"]["tests"]["needs"]
    # CLI committed-output comparisons remain separate from generator tests.
    cli = (ROOT / ".github/workflows/cli-reference.yml").read_text()
    assert "--check" in cli
