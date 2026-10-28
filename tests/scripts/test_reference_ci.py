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
    assert check["if"] == (
        "matrix.node == 22 && !(fromJSON(steps.scope.outputs.scope).node_generated && "
        "((github.event_name == 'push' && github.ref == 'refs/heads/main') || "
        "(github.event_name == 'pull_request' && github.event.pull_request.base.ref == 'main')))"
    )
    checkout = next(step for step in steps if "checkout@" in step.get("uses", ""))["with"]
    assert checkout["fetch-depth"] == 0
    assert checkout["ref"] == "${{ github.event.pull_request.head.sha || github.sha }}"
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


@pytest.mark.parametrize("event", ["pull_request", "push", "workflow_dispatch"])
@pytest.mark.parametrize("target", ["main", "release", "feature"])
@pytest.mark.parametrize("generated", [False, True])
def test_freshness_owner_depends_on_ci_event_and_target(event: str, target: str, generated: bool) -> None:
    reference = yaml.safe_load((ROOT / ".github/workflows/typescript-sdk-reference.yml").read_text())
    job = reference["jobs"]["generated-reference"]
    condition = next(step["if"] for step in job["steps"] if step.get("run") == "npm run docs:check")
    reference_checks = 0
    for node in job["strategy"]["matrix"]["node"]:
        expression = condition.replace("matrix.node", str(node)).replace("github.event_name", repr(event))
        expression = expression.replace("github.event.pull_request.base.ref", repr(target))
        expression = expression.replace("github.ref", repr(f"refs/heads/{target}"))
        expression = expression.replace("fromJSON(steps.scope.outputs.scope).node_generated", str(generated))
        expression = expression.replace("&&", "and").replace("||", "or").replace("!", "not ")
        reference_checks += int(eval(expression, {"__builtins__": {}}))
    # The coordinating CI workflow runs only for main pushes and main-targeted PRs.
    coordinating_ci = event in {"pull_request", "push"} and target == "main"
    node_checks = int(coordinating_ci and generated)
    assert reference_checks + node_checks == 1
    assert reference_checks == int(not (coordinating_ci and generated))


def test_reference_and_coordinating_ci_select_from_same_immutable_revision() -> None:
    configurations = [
        yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
        for name in ("typescript-sdk-reference.yml", "ci.yml")
    ]
    jobs = [configurations[0]["jobs"]["generated-reference"], configurations[1]["jobs"]["changes"]]
    refs = [next(step for step in job["steps"] if "checkout@" in step.get("uses", ""))["with"]["ref"] for job in jobs]
    assert refs == ["${{ github.event.pull_request.head.sha || github.sha }}"] * 2
