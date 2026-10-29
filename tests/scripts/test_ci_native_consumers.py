"""Native dependency routing and the commands selected by real Git diffs."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts import ci_integration_examples as runner
from scripts import ci_scope as ci
from tests.scripts import test_ci_scope as history_tests
from tests.scripts.test_ci_integration_examples import agent_phases, calls, shipped_project

pytest_plugins = ["tests.scripts.test_ci_integration_examples"]

ROOT = Path(__file__).resolve().parents[2]
PYTHON_ONLY = {"boat", "daytona", "e2b", "openagi", "prime-intellect", "yutori"}
NODE_ONLY = {"agentcard", "e2e", "eve", "fx", "trigger"}
PUBLISHED_ONLY = {"docker-sandboxes", "inngest", "temporal"}
NON_SDK = {"replit", "terraform-profiles", "valtown"}
CROSS_LANGUAGE = {
    "agent-browser",
    "anthropic-computer-use",
    "box",
    "braintrust",
    "claude-agents",
    "deepagents",
    "gemini-computer-use",
    "github-actions",
    "laminar",
    "mongodb",
    "onepassword",
    "openai-agents",
    "openai-computer-use",
    "pipedream",
    "selenium",
    "stripe-link",
    "tzafon",
    "watsonx",
}


@pytest.fixture
def history() -> Iterator[history_tests.GitHistoryTests]:
    fixture = history_tests.GitHistoryTests()
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.doCleanups()


def test_dependency_inventory_covers_registered_projects_and_real_manifests() -> None:
    assert set(ci.INTEGRATION_DEPENDENCIES) == set(ci.INTEGRATION_EXAMPLES)
    assert PYTHON_ONLY | NODE_ONLY | PUBLISHED_ONLY | NON_SDK | CROSS_LANGUAGE == set(ci.INTEGRATION_EXAMPLES)
    for name in PYTHON_ONLY | NODE_ONLY | CROSS_LANGUAGE | PUBLISHED_ONLY:
        project = ROOT / "examples" / name
        dependencies = ci.INTEGRATION_DEPENDENCIES[name]
        if "python-source" in dependencies and name not in runner.RECIPES:
            manifest = project / (
                "requirements.txt" if name in {"box", "gemini-computer-use", "selenium", "yutori"} else "pyproject.toml"
            )
            assert "notte-sdk" in manifest.read_text(), name
        if dependencies & {"node-source", "node-published"} and name not in runner.RECIPES:
            manifest = project / ("package.json" if (project / "package.json").exists() else "typescript/package.json")
            assert "notte-sdk" in json.loads(manifest.read_text())["dependencies"], name
    assert "notte-sdk" not in (ROOT / "examples/replit/package.json").read_text()
    assert "fetch(" in (ROOT / "examples/valtown/main.ts").read_text()


@pytest.mark.parametrize(
    "path",
    [
        "packages/notte-sdk/src/notte_sdk/client.py",
        "packages/notte-sdk/src/notte_sdk/_generated/models.py",
        "packages/notte-sdk/src/notte_sdk/_generated/schema_index.json",
        "packages/notte-core/src/notte_core/types.py",
        "packages/notte-core/src/notte_core/schema.py",
        "packages/notte-core/pyproject.toml",
        "src/notte/__init__.py",
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        ".github/actions/python-setup/action.yml",
    ],
)
def test_python_source_inputs_select_python_consumers_on_both_events(
    history: history_tests.GitHistoryTests,
    path: str,
) -> None:
    head = history.commit({path: "changed input\n"})
    for event in ("pull_request", "push"):
        scope = history.scope(event, history.base, head)
        assert set(scope["integration_examples"]) == PYTHON_ONLY | CROSS_LANGUAGE
        assert scope["integration_source_only"] == scope["integration_examples"]
        assert scope["paired_live"] and scope["paired_static"]


@pytest.mark.parametrize(
    "path",
    [
        "node-sdk/src/session.ts",
        "node-sdk/src/lib/client/types.gen.ts",
        "node-sdk/src/resources.gen.ts",
        "node-sdk/package.json",
        "node-sdk/package-lock.json",
        "node-sdk/tsconfig.json",
        "node-sdk/tsup.config.ts",
        "node-sdk/new-build.config.json",
    ],
)
def test_node_inputs_select_node_source_consumers_on_both_events(
    history: history_tests.GitHistoryTests,
    path: str,
) -> None:
    head = history.commit({path: "changed input\n"})
    for event in ("pull_request", "push"):
        scope = history.scope(event, history.base, head)
        assert set(scope["integration_examples"]) == NODE_ONLY | CROSS_LANGUAGE
        assert scope["integration_source_only"] == scope["integration_examples"]


@pytest.mark.parametrize(
    "path,expected",
    [
        ("docs/src/testers/integrations/openai_agents.py", {"openai-agents"}),
        ("docs/src/testers/integrations/claude_agents.ts", {"claude-agents"}),
        ("node-sdk/test/helpers/run-openai-recipe.py", {"openai-agents"}),
        ("docs/src/sniptest/run_python.py", {"agent-browser", "claude-agents", "mongodb", "openai-agents"}),
        ("docs/src/sniptest/run_typescript.mjs", {"agent-browser", "claude-agents", "mongodb", "openai-agents"}),
        ("docs/src/sniptest/typescript-loader.mjs", {"agent-browser", "claude-agents", "mongodb", "openai-agents"}),
        ("node-sdk/test/helpers/session-closure.ts", {"agent-browser", "mongodb", "claude-agents", "openai-agents"}),
        ("docs/package-lock.json", {"claude-agents", "openai-agents", "mongodb"}),
        ("examples/braintrust/python/demo.py", {"braintrust"}),
        ("examples/braintrust/typescript/package-lock.json", {"braintrust"}),
        ("examples/yutori/requirements.txt", {"yutori"}),
        ("examples/temporal/package-lock.json", {"temporal"}),
        ("examples/replit/test/mcp.live.test.mjs", {"replit"}),
    ],
)
def test_project_and_cross_language_recipe_inputs_keep_full_compatibility(
    history: history_tests.GitHistoryTests,
    path: str,
    expected: set[str],
) -> None:
    head = history.commit({path: "changed input\n"})
    for event in ("pull_request", "push"):
        scope = history.scope(event, history.base, head)
        assert set(scope["integration_examples"]) == expected
        assert scope["integration_source_only"] == []


@pytest.mark.parametrize("path", ["openapi/openapi.json", "openapi/resources.json"])
def test_shared_wire_schema_covers_both_sdks_and_raw_api_consumers(
    history: history_tests.GitHistoryTests,
    path: str,
) -> None:
    head = history.commit({path: "{}\n"})
    for event in ("pull_request", "push"):
        scope = history.scope(event, history.base, head)
        assert set(scope["integration_examples"]) == PYTHON_ONLY | NODE_ONLY | CROSS_LANGUAGE | {
            "terraform-profiles",
            "valtown",
        }
        assert set(scope["integration_source_only"]) == PYTHON_ONLY | NODE_ONLY | CROSS_LANGUAGE


@pytest.mark.parametrize(
    "path",
    [
        "scripts/ci_scope.py",
        "scripts/ci_integration_examples.py",
        "tests/scripts/test_ci_native_consumers.py",
        ".github/workflows/paired-sdk-examples.yml",
        "scripts/new_runner.py",
        "new-runtime/config.json",
        "Makefile",
    ],
)
def test_shared_harness_and_unknown_inputs_are_conservative_on_both_events(
    history: history_tests.GitHistoryTests,
    path: str,
) -> None:
    head = history.commit({path: "changed input\n"})
    for event in ("pull_request", "push"):
        scope = history.scope(event, history.base, head)
        assert scope["integration_examples"] == sorted(ci.INTEGRATION_EXAMPLES)
        assert scope["integration_source_only"] == []
        assert scope["paired_live"]


def test_unclassified_future_registration_runs_full_for_either_sdk(
    history: history_tests.GitHistoryTests, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ci, "INTEGRATION_EXAMPLES", {**ci.INTEGRATION_EXAMPLES, "future": "node-project"})
    head = history.commit(
        {"packages/notte-sdk/src/notte_sdk/client.py": "changed\n", "node-sdk/src/session.ts": "changed\n"}
    )
    for event in ("pull_request", "push"):
        scope = history.scope(event, history.base, head)
        assert "future" in scope["integration_examples"]
        assert "future" not in scope["integration_source_only"]


def test_mixed_diff_full_project_mode_dominates_source_mode(history: history_tests.GitHistoryTests) -> None:
    history.commit({"packages/notte-sdk/src/notte_sdk/client.py": "changed\n"})
    head = history.commit({"node-sdk/src/session.ts": "changed\n", "examples/braintrust/python/demo.py": "changed\n"})
    for event in ("pull_request", "push"):
        scope = history.scope(event, history.base, head)
        assert set(scope["integration_examples"]) == PYTHON_ONLY | NODE_ONLY | CROSS_LANGUAGE
        assert set(scope["integration_source_only"]) == (PYTHON_ONLY | NODE_ONLY | CROSS_LANGUAGE) - {"braintrust"}


def test_renamed_and_deleted_paths_retain_both_dependencies(history: history_tests.GitHistoryTests) -> None:
    before = history.commit({"packages/notte-sdk/src/notte_sdk/old.py": "changed\n"})
    (history.repo / "node-sdk/src").mkdir(parents=True)
    history.git("mv", "packages/notte-sdk/src/notte_sdk/old.py", "node-sdk/src/new.ts")
    head = history.commit({})
    for event in ("pull_request", "push"):
        scope = history.scope(event, before, head)
        assert set(scope["integration_examples"]) == PYTHON_ONLY | NODE_ONLY | CROSS_LANGUAGE
    (history.repo / "node-sdk/src/new.ts").unlink()
    deleted = history.commit({})
    for event in ("pull_request", "push"):
        assert set(history.scope(event, head, deleted)["integration_examples"]) == NODE_ONLY | CROSS_LANGUAGE


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch", "reviewed_push"])
def test_periodic_and_full_runs_keep_all_published_and_hosted_coverage(event: str) -> None:
    scope = ci.select(event, "", "")
    assert scope["integration_examples"] == sorted(ci.INTEGRATION_EXAMPLES)
    assert scope["integration_source_only"] == []


@pytest.mark.parametrize("name", ["agentcard", "openai-computer-use", "github-actions", "braintrust", "openagi"])
@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_sdk_diff_drives_source_install_before_native_execution(
    history: history_tests.GitHistoryTests,
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    event: str,
) -> None:
    # Command stubs remain first; the Git-history fixture also needs the system Git.
    monkeypatch.setenv("PATH", os.environ["PATH"] + os.pathsep + os.defpath)
    path = "node-sdk/src/session.ts" if name == "agentcard" else "packages/notte-sdk/src/notte_sdk/client.py"
    head = history.commit({path: "changed\n"})
    scope = history.scope(event, history.base, head)
    assert name in scope["integration_examples"]
    project = shipped_project(workspace, monkeypatch, name, ci.INTEGRATION_EXAMPLES[name])
    (project / "typescript").mkdir(exist_ok=True)
    (project / "test_native.py").write_text("# Native command fixture\n")
    monkeypatch.setenv(
        "INTEGRATION_SOURCE_ONLY", json.dumps([name] if name in scope["integration_source_only"] else [])
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge" if event == "pull_request" else "refs/heads/main")
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["credentials"]]
    assert native
    expected_credentials = (
        ["NOTTE_API_KEY", "OPENAI_API_KEY"] if event == "push" and name == "openai-computer-use" else ["NOTTE_API_KEY"]
    )
    assert all(call["credentials"] == expected_credentials for call in native)
    source = next(
        index
        for index, call in enumerate(observed)
        if "-e" in call["args"] or call["args"] == ["npm", "install", "--no-save", str(workspace / "node-sdk")]
    )
    assert all(observed.index(call) > source for call in native)
    assert len(native) == (2 if name in {"openai-computer-use", "github-actions"} else 1)
    if name == "agentcard":
        assert not any("unittest" in call["args"] for call in observed)
    if name == "openagi":
        assert not any(call["args"][0] == "npm" for call in observed)


@pytest.mark.parametrize("name", ["openai-agents", "claude-agents", "mongodb", "agent-browser"])
def test_recipe_source_selection_keeps_cross_language_driver(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    shipped_project(workspace, monkeypatch, name, "NOTTE_DOCS_PYTHON")
    monkeypatch.setenv("INTEGRATION_SOURCE_ONLY", json.dumps([name]))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")
    if name in runner.AGENT_RECIPES:
        agent_phases(monkeypatch)
    else:
        runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["credentials"]]
    assert any(f"test/{name}.integration.test.ts" in call["args"] for call in native)
    assert all(call["docs_python"] == str(workspace / ".venv/bin/python") for call in native)
    expected_credentials = {
        "openai-agents": {"NOTTE_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"},
        "claude-agents": {"NOTTE_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_AUTH_TOKEN"},
        "mongodb": {"NOTTE_API_KEY", "MONGODB_URI"},
        "agent-browser": {"NOTTE_API_KEY"},
    }[name]
    assert all(set(call["credentials"]) == expected_credentials for call in native)


def test_source_failure_keeps_original_exit_and_stops(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = shipped_project(workspace, monkeypatch, "openai-computer-use", "NOTTE_COMPUTER_USE_PYTHON")
    (project / "typescript").mkdir()
    monkeypatch.setenv("INTEGRATION_SOURCE_ONLY", '["openai-computer-use"]')
    monkeypatch.setenv("FAIL_NATIVE", "1")
    with pytest.raises(subprocess.CalledProcessError) as failure:
        runner.main()
    assert failure.value.returncode == 23
    assert calls(workspace)[-1]["args"] == ["npm", "run", "test:live"]


@pytest.mark.parametrize("selection", ['"alpha"', "[1]", '["unselected"]'])
def test_invalid_source_selection_fails_before_installs(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection: str,
) -> None:
    monkeypatch.setenv("INTEGRATION_SOURCE_ONLY", selection)
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    with pytest.raises(ValueError, match="INTEGRATION_SOURCE_ONLY"):
        runner.main()
    assert calls(workspace) == []


@pytest.mark.parametrize(
    "name,expected", [("agentcard", 2), ("openai-computer-use", 4), ("inngest", 1), ("temporal", 1), ("replit", 1)]
)
def test_full_scope_executes_published_source_or_hosted_legs(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    expected: int,
) -> None:
    scope = ci.select("workflow_dispatch", "", "")
    assert name in scope["integration_examples"]
    project = shipped_project(workspace, monkeypatch, name, ci.INTEGRATION_EXAMPLES[name])
    (project / "typescript").mkdir(exist_ok=True)
    monkeypatch.setenv("INTEGRATION_SOURCE_ONLY", json.dumps(scope["integration_source_only"]))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["credentials"]]
    assert len(native) == expected
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in native)
    installs = [
        call for call in observed if call["args"] == ["npm", "install", "--no-save", str(workspace / "node-sdk")]
    ]
    if name in {"agentcard", "openai-computer-use"}:
        assert len(installs) == 1
        native_positions = [index for index, call in enumerate(observed) if call["credentials"]]
        assert native_positions[0] < observed.index(installs[0]) < native_positions[-1]
    else:
        assert installs == []


def test_workflow_transmits_source_selection_without_changing_secret_guards() -> None:
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/paired-sdk-examples.yml").read_text())
    live = workflow["jobs"]["live"]
    native = next(step for step in live["steps"] if "ci_integration_examples.py live" in step.get("run", ""))
    assert (
        native["env"]["INTEGRATION_SOURCE_ONLY"]
        == "${{ toJSON(fromJSON(needs.changes.outputs.scope).integration_source_only || fromJSON('[]')) }}"
    )
    assert "github.event.pull_request.head.repo.full_name == github.repository" in live["if"]
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        assert "github.ref == 'refs/heads/main' && github.event_name != 'pull_request'" in native["env"][key]


def test_agent_jobs_supply_credentials_only_after_dependency_preparation() -> None:
    import yaml

    config = yaml.safe_load((ROOT / ".github/workflows/paired-sdk-examples.yml").read_text())
    shared = config["jobs"]["live"]
    native = next(step for step in shared["steps"] if "ci_integration_examples.py live" in step.get("run", ""))
    assert "OPENROUTER_API_KEY" not in native["env"]
    job = config["jobs"]["agent-models"]
    assert job["needs"] == "changes"
    assert "github.event.pull_request.head.repo.full_name == github.repository" in job["if"]
    assert "github.ref == 'refs/heads/main'" in job["if"]
    for name in runner.AGENT_RECIPES:
        assert name in job["strategy"]["matrix"]["recipe"]
    assert not any("secrets." in str(value) for value in job["env"].values())
    prepare = next(step for step in job["steps"] if "prepare-agent" in step.get("run", ""))
    execute = next(step for step in job["steps"] if "test-agent" in step.get("run", ""))
    assert job["steps"].index(prepare) < job["steps"].index(execute)
    assert "secrets." not in str(prepare)
    assert set(execute["env"]) == {"NOTTE_API_KEY", "OPENROUTER_API_KEY"}
    assert not any("secrets." in str(step) for step in job["steps"] if step is not execute)
