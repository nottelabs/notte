"""Exercise native runner isolation, SDK resolution, sharding, and failure propagation."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts import ci_integration_examples as runner


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({name: "NOTTE_COMPUTER_USE_PYTHON" for name in ("alpha", "beta", "gamma")}))
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "REGISTRY", registry)
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["gamma", "alpha", "beta", "alpha"]')
    monkeypatch.setenv("COMMAND_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv("NOTTE_API_KEY", "fixture-ci-key")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-provider-key")
    stub = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = [Path(sys.argv[0]).name, *sys.argv[1:]]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps({'args': args, 'cwd': os.getcwd(),
        'credentials': sorted(k for k in ('NOTTE_API_KEY', 'OPENAI_API_KEY') if os.environ.get(k)),
        'python': os.environ.get('NOTTE_COMPUTER_USE_PYTHON'),
        'gemini_live': os.environ.get('NOTTE_GEMINI_LIVE'),
        'gemini_model': os.environ.get('NOTTE_GEMINI_MODEL_LIVE')}) + '\\n')
if os.environ.get('FAIL_UNITTEST') and 'unittest' in args:
    sys.exit(19)
"""
    for path in (tmp_path / "bin/uv", tmp_path / "bin/npm"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stub)
        path.chmod(0o755)
    for name in ("alpha", "beta", "gamma"):
        project = tmp_path / "examples" / name
        (project / "typescript").mkdir(parents=True)
        python = project / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text(stub)
        python.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    return tmp_path


def calls(workspace: Path) -> list[dict]:
    path = workspace / "calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_shards_partition_projects_once(workspace: Path) -> None:
    first = runner.projects("1/2")
    second = runner.projects("2/2")
    assert [name for name, _ in first] == ["alpha", "gamma"]
    assert [name for name, _ in second] == ["beta"]
    assert len(first + second) == 3
    assert calls(workspace) == []


def test_live_resolves_both_sdks_and_limits_credentials(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["alpha"]')
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    runner.main()
    observed = calls(workspace)
    tests = [call for call in observed if "unittest" in call["args"] or "test:live" in call["args"]]
    assert len(tests) == 4
    assert all(call["credentials"] == ["NOTTE_API_KEY", "OPENAI_API_KEY"] for call in tests)
    assert all(call["python"] == str(workspace / "examples/alpha/.venv/bin/python") for call in tests)
    assert all(not call["credentials"] for call in observed if call not in tests)
    commands = [call["args"] for call in observed]
    assert commands[0] == ["uv", "sync", "--locked"]
    source = next(command for command in commands if command[:3] == ["uv", "pip", "install"])
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert "--no-deps" not in source
    assert ["npm", "install", "--no-save", "--package-lock=false", str(workspace / "node-sdk")] in commands
    assert commands.count(["npm", "run", "typecheck"]) == 2
    assert len([command for command in commands if command[:3] == ["uv", "pip", "check"]]) == 2
    assert commands.index(source) > commands.index(tests[1]["args"])


def test_native_failure_stops_runner(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["alpha"]')
    monkeypatch.setenv("FAIL_UNITTEST", "1")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    with pytest.raises(subprocess.CalledProcessError) as failure:
        runner.main()
    assert failure.value.returncode == 19
    assert calls(workspace)[-1]["args"][1:3] == ["-m", "unittest"]
    assert not any(call["args"][:3] == ["uv", "pip", "install"] for call in calls(workspace))


def test_missing_credentials_fail_before_installs(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTTE_API_KEY")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    with pytest.raises(ValueError, match="NOTTE_API_KEY"):
        runner.main()
    assert calls(workspace) == []


@pytest.mark.parametrize("selected", ['["../escape"]', '["unregistered"]', '"alpha"', "[1]"])
def test_invalid_selection_fails_before_installs(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, selected: str
) -> None:
    monkeypatch.setenv("INTEGRATION_EXAMPLES", selected)
    with pytest.raises(ValueError):
        runner.projects("1/2")
    assert calls(workspace) == []


def test_gemini_root_commands_preserve_offline_and_paid_boundaries(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.REGISTRY.write_text(json.dumps({"gemini-computer-use": "gemini-root"}))
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["gemini-computer-use"]')
    monkeypatch.setenv("NOTTE_GEMINI_MODEL_LIVE", "1")
    project = workspace / "examples/gemini-computer-use"
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
    python.chmod(0o755)
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    runner.main()
    observed = calls(workspace)
    native_tests = [call for call in observed if "unittest" in call["args"] or call["args"] == ["npm", "test"]]
    assert len(native_tests) == 6
    assert all(call["cwd"] == str(project) for call in native_tests)
    assert all(call["gemini_model"] == "0" for call in native_tests)
    assert all(call["gemini_live"] == "0" and not call["credentials"] for call in native_tests[:2])
    assert all(call["gemini_live"] == "1" and call["credentials"] for call in native_tests[2:])
    assert all(call["python"] is None for call in observed)
    assert all(not call["credentials"] for call in observed if call not in native_tests)
    commands = [call["args"] for call in observed]
    assert commands[0] == ["uv", "venv", str(project / ".venv"), "--clear", "--python", "3.11"]
    assert ["uv", "pip", "install", "--python", str(python), "-r", "requirements.txt"] in commands
    assert commands.count([python.name, "-m", "unittest", "-v", "test_agent.py"]) == 3
    assert commands.count(["npm", "test"]) == 3
    assert commands.count(["npm", "run", "typecheck"]) == 2
    source = next(command for command in commands if "-e" in command)
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert "--no-deps" not in source
    assert ["npm", "install", "--no-save", "--package-lock=false", str(workspace / "node-sdk")] in commands
    assert len([command for command in commands if command[:3] == ["uv", "pip", "check"]]) == 2
