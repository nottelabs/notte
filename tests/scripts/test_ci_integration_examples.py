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
    monkeypatch.delenv("BRAINTRUST_API_KEY", raising=False)
    stub = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = [Path(sys.argv[0]).name, *sys.argv[1:]]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps({'args': args, 'cwd': os.getcwd(),
        'credentials': sorted(k for k in ('NOTTE_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'BRAINTRUST_API_KEY', 'LMNR_PROJECT_API_KEY', 'OP_SERVICE_ACCOUNT_TOKEN') if os.environ.get(k)),
        'vitest': os.environ.get('VITEST_INTEGRATION'),
        'journal': os.environ.get('NOTTE_AGENT_BROWSER_OWNERSHIP_JOURNAL'),
        'example_python': os.environ.get('NOTTE_EXAMPLE_PYTHON'),
        'docs_python': os.environ.get('NOTTE_DOCS_PYTHON'),
        'mongodb_uri': os.environ.get('MONGODB_URI'),
        'python': os.environ.get('NOTTE_COMPUTER_USE_PYTHON'),
        'braintrust_python': os.environ.get('NOTTE_BRAINTRUST_PYTHON'),
        'braintrust_project': os.environ.get('BRAINTRUST_PROJECT'),
        'onepassword_python': os.environ.get('NOTTE_ONEPASSWORD_PYTHON'),
        'gemini_live': os.environ.get('NOTTE_GEMINI_LIVE'),
        'gemini_model': os.environ.get('NOTTE_GEMINI_MODEL_LIVE'),
        'selenium_live': os.environ.get('NOTTE_SELENIUM_LIVE'),
        'live_flags': {k: v for k, v in os.environ.items() if k.startswith('NOTTE_') and k.endswith('_LIVE')},
        'tracing': os.environ.get('LANGSMITH_TRACING'),
        'driver': os.environ.get('CHROMEDRIVER_PATH')}) + '\\n')
if args[0] == 'docker':
    if os.environ.get('FAIL_DOCKER') == args[1]:
        sys.exit(31)
    if args[1] == 'inspect':
        print(os.environ.get('MONGO_HEALTH', 'healthy'))
if args[1:] == ['install_driver.py']:
    print(os.environ['DRIVER_OUTPUT'])
    print('Driver setup diagnostic', file=sys.stderr)
    if os.environ.get('FAIL_DRIVER'):
        sys.exit(17)
if os.environ.get('FAIL_UNITTEST') and 'unittest' in args:
    sys.exit(19)
if os.environ.get('FAIL_TS_DRIVER') and args == ['npm', 'run', 'test:live']:
    sys.exit(19)
if os.environ.get('FAIL_NATIVE') and ('test:live' in args or any(arg.endswith('.integration.test.ts') for arg in args)):
    sys.exit(23)
"""
    for path in (tmp_path / "bin/uv", tmp_path / "bin/npm", tmp_path / "bin/npx", tmp_path / "bin/docker"):
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
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner-temp"))
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


@pytest.mark.parametrize("shard", ["0/1", "2/1", "1/0", "bad", "1/2/3"])
def test_invalid_shard_cli_fails_before_credentials_or_installs(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, shard: str
) -> None:
    monkeypatch.setattr("sys.argv", ["runner", "live", "--shard", shard])
    monkeypatch.delenv("NOTTE_API_KEY")
    with pytest.raises(ValueError):
        runner.main()
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


@pytest.fixture
def selenium_project(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runner.REGISTRY.write_text(json.dumps({"selenium": "selenium-root"}))
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["selenium"]')
    project = workspace / "examples/selenium"
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
    python.chmod(0o755)
    driver = project / ".drivers/150/chromedriver"
    driver.parent.mkdir(parents=True)
    driver.write_text("fixture driver")
    driver.chmod(0o755)
    monkeypatch.setenv("DRIVER_OUTPUT", str(driver))
    return project


def test_selenium_runs_driver_only_in_live_modes(
    workspace: Path, selenium_project: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    runner.main()
    observed = calls(workspace)
    drivers = [call for call in observed if call["args"][1:] == ["install_driver.py"]]
    live_tests = [
        call for call in observed if "test_selenium" in call["args"] or call["args"] == ["npm", "run", "test:live"]
    ]
    assert len(drivers) == 2
    assert len(live_tests) == 4
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in drivers + live_tests)
    assert all(call["selenium_live"] == "1" for call in drivers + live_tests)
    assert all(call["driver"] == str(selenium_project / ".drivers/150/chromedriver") for call in live_tests)
    assert all(call["cwd"] == str(selenium_project) for call in drivers + live_tests)
    assert all(not call["credentials"] for call in observed if call not in drivers + live_tests)
    assert "Driver setup diagnostic" in capfd.readouterr().err
    commands = [call["args"] for call in observed]
    assert commands[0][-2:] == ["--python", "3.12"]
    assert ["python", "-m", "unittest", "-v", "test_bridge"] in commands
    assert ["npm", "test"] in commands
    assert len([command for command in commands if command[:3] == ["uv", "pip", "check"]]) == 2
    source = next(command for command in commands if "-e" in command)
    assert "--no-deps" not in source
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert commands.index(source) > commands.index(live_tests[1]["args"])


@pytest.mark.parametrize("invalid", ["empty", "relative", "outside", "multiple", "missing", "nonexecutable"])
def test_selenium_rejects_invalid_driver_output_before_live_tests(
    workspace: Path, selenium_project: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    driver = selenium_project / ".drivers/150/chromedriver"
    outputs = {
        "empty": "",
        "relative": ".drivers/150/chromedriver",
        "outside": str(workspace / "other"),
        "multiple": str(driver) + "\nextra",
        "missing": str(driver.parent / "missing"),
        "nonexecutable": str(driver),
    }
    if invalid == "nonexecutable":
        driver.chmod(0o644)
    monkeypatch.setenv("DRIVER_OUTPUT", outputs[invalid])
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    with pytest.raises(ValueError, match="owned executable driver"):
        runner.main()
    assert not any("test_selenium" in call["args"] for call in calls(workspace))
    assert not any("-e" in call["args"] for call in calls(workspace))


def test_selenium_driver_failure_stops_before_browser_tests(
    workspace: Path, selenium_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAIL_DRIVER", "1")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    with pytest.raises(subprocess.CalledProcessError) as failure:
        runner.main()
    assert failure.value.returncode == 17
    assert calls(workspace)[-1]["args"][1:] == ["install_driver.py"]
    assert not any("test_selenium" in call["args"] for call in calls(workspace))


@pytest.mark.parametrize("name,module", [("deepagents", "test_agent.py"), ("laminar", "test_read_page.py")])
def test_root_unittest_preserves_independent_suites_and_offline_boundaries(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, module: str
) -> None:
    runner.REGISTRY.write_text(json.dumps({name: "root-unittest"}))
    monkeypatch.setenv("INTEGRATION_EXAMPLES", json.dumps([name]))
    prefix = f"NOTTE_{name.upper()}"
    monkeypatch.setenv(f"{prefix}_MODEL_LIVE", "1")
    monkeypatch.setenv(f"{prefix}_EXPORT_LIVE", "1")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    project = workspace / "examples" / name
    (project / "typescript").mkdir(parents=True)
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
    python.chmod(0o755)
    (project / "worker.py").write_text("# Fixture source\n")
    (project / module).write_text("# Fixture unittest module\n")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    runner.main()
    observed = calls(workspace)
    suites = [call for call in observed if "unittest" in call["args"] or "test:live" in call["args"]]
    assert len(suites) == 6
    assert all(call["args"] == ["python", "-m", "unittest", "-v", module] for call in suites[::2])
    assert all(call["cwd"] == str(project) for call in suites[::2])
    assert all(call["cwd"] == str(project / "typescript") for call in suites[1::2])
    assert all(call["live_flags"][f"{prefix}_LIVE"] == "0" and not call["credentials"] for call in suites[:2])
    assert all(call["live_flags"][f"{prefix}_LIVE"] == "1" and call["credentials"] for call in suites[2:])
    assert all(call["live_flags"][f"{prefix}_MODEL_LIVE"] == "1" for call in suites[2:])
    assert all(call["live_flags"][f"{prefix}_EXPORT_LIVE"] == "1" for call in suites[2:])
    assert all(call["tracing"] == "false" for call in observed)
    assert all(not call["credentials"] for call in observed if call not in suites[2:])
    assert all(value == "0" for call in observed if call not in suites[2:] for value in call["live_flags"].values())
    commands = [call["args"] for call in observed]
    assert ["python", "-m", "compileall", "-q", module, "worker.py"] in commands
    assert commands.count(["uv", "sync", "--locked"]) == 1
    assert len([command for command in commands if command[:3] == ["uv", "pip", "check"]]) == 2
    assert any(command[-1:] == [str(workspace / "node-sdk")] for command in commands)


def test_root_unittest_requires_real_modules_before_setup(workspace: Path) -> None:
    with pytest.raises(ValueError, match="requires root test_"):
        runner.check(workspace / "examples/alpha", {}, "root-unittest")
    assert calls(workspace) == []


def test_laminar_vendor_credential_is_absent_from_install_and_offline_commands(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.REGISTRY.write_text(json.dumps({"laminar": "root-unittest"}))
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["laminar"]')
    monkeypatch.setenv("LMNR_PROJECT_API_KEY", "fixture-vendor-key")
    monkeypatch.setenv("NOTTE_LAMINAR_EXPORT_LIVE", "1")
    project = workspace / "examples/laminar"
    (project / "typescript").mkdir(parents=True)
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
    python.chmod(0o755)
    (project / "test_read_page.py").write_text("# Fixture unittest module\n")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    runner.main()
    observed = calls(workspace)
    suites = [call for call in observed if "unittest" in call["args"] or "test:live" in call["args"]]
    assert len(suites) == 6
    assert all(not call["credentials"] for call in observed if call not in suites[2:])
    assert all(call["live_flags"]["NOTTE_LAMINAR_EXPORT_LIVE"] == "0" for call in suites[:2])
    assert all("LMNR_PROJECT_API_KEY" in call["credentials"] for call in suites[2:])
    assert all(call["live_flags"]["NOTTE_LAMINAR_EXPORT_LIVE"] == "1" for call in suites[2:])
    assert [call["args"] for call in suites[::2]] == [["python", "-m", "unittest", "-v", "test_read_page.py"]] * 3


@pytest.mark.parametrize("failure", [False, True])
def test_braintrust_ts_driver_preserves_python_selection_and_credential_isolation(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    project = workspace / "examples/braintrust"
    (project / "typescript").mkdir(parents=True)
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
    python.chmod(0o755)
    runner.REGISTRY.write_text(json.dumps({"braintrust": "typescript-driver"}))
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["braintrust"]')
    monkeypatch.setenv("BRAINTRUST_API_KEY", "fixture-trace-key")
    monkeypatch.setenv("BRAINTRUST_PROJECT", "notte-integration-tests")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    if failure:
        monkeypatch.setenv("FAIL_TS_DRIVER", "1")
        with pytest.raises(subprocess.CalledProcessError) as error:
            runner.main()
        assert error.value.returncode == 19
    else:
        runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["args"] == ["npm", "run", "test:live"]]
    assert len(native) == (1 if failure else 2)
    assert all(call["cwd"] == str(project / "typescript") for call in native)
    assert all(call["braintrust_python"] == str(project / ".venv/bin/python") for call in native)
    assert all(call["braintrust_project"] == "notte-integration-tests" for call in native)
    assert all(call["credentials"] == ["BRAINTRUST_API_KEY", "NOTTE_API_KEY", "OPENAI_API_KEY"] for call in native)
    assert all(not call["credentials"] for call in observed if call not in native)
    assert not any("unittest" in call["args"] for call in observed)
    commands = [call["args"] for call in observed]
    assert ["python", "-c", "from braintrust import init_logger; from notte_sdk import NotteClient"] in commands
    overlays = [command for command in commands if command[:3] == ["uv", "pip", "install"]]
    if failure:
        assert not overlays
    else:
        assert len(overlays) == 1 and "--no-deps" not in overlays[0]
        assert commands.index(overlays[0]) > commands.index(native[0]["args"])


def shipped_project(workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, convention: str) -> Path:
    runner.REGISTRY.write_text(json.dumps({name: convention}))
    monkeypatch.setenv("INTEGRATION_EXAMPLES", json.dumps([name]))
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    for directory in (workspace / "examples" / name, workspace / "node-sdk", workspace / "docs"):
        directory.mkdir(parents=True, exist_ok=True)
    for python in (workspace / "examples" / name / ".venv/bin/python", workspace / ".venv/bin/python"):
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
        python.chmod(0o755)
    return workspace / "examples" / name


@pytest.mark.parametrize("name,count", [("trigger", 2), ("inngest", 1), ("temporal", 1)])
def test_node_projects_keep_existing_sdk_modes_and_no_paid_pr_calls(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, count: int
) -> None:
    project = shipped_project(workspace, monkeypatch, name, "node-project")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-other-provider")
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["args"] == ["npm", "run", "test:live"]]
    assert len(native) == count
    assert all(call["credentials"] == ["NOTTE_API_KEY"] and call["cwd"] == str(project) for call in native)
    assert all(not call["credentials"] for call in observed if call not in native)
    commands = [call["args"] for call in observed]
    source = [command for command in commands if command[:2] == ["npm", "install"]]
    assert len(source) == count - 1
    if source:
        assert source[0] == ["npm", "install", "--no-save", "--package-lock=false", str(workspace / "node-sdk")]
        assert commands.count(["npm", "test"]) == 3
        assert commands.count(["npm", "run", "typecheck"]) == 3
    if name == "inngest":
        assert native[0]["live_flags"]["NOTTE_INNGEST_MODEL_LIVE"] == "0"
    if name == "temporal":
        assert ["npm", "run", "build"] in commands
    assert not any("test:hosted" in command for command in commands)


@pytest.mark.parametrize(
    "name,provider",
    [
        ("openai-agents", "OPENAI_API_KEY"),
        ("claude-agents", "ANTHROPIC_API_KEY"),
        ("agent-browser", None),
        ("inngest", "ANTHROPIC_API_KEY"),
    ],
)
def test_framework_commands_restrict_credentials_and_preserve_special_checks(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, provider: str | None
) -> None:
    shipped_project(workspace, monkeypatch, name, "node-project" if name == "inngest" else "NOTTE_DOCS_PYTHON")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-other-provider")
    monkeypatch.setenv("GEMINI_API_KEY", "fixture-unused-provider")
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["credentials"]]
    expected = sorted(["NOTTE_API_KEY", provider]) if provider else ["NOTTE_API_KEY"]
    assert native and all(call["credentials"] == expected for call in native)
    assert all("vitest" in call["args"] or "unittest" in call["args"] or "test:live" in call["args"] for call in native)
    commands = [call["args"] for call in observed]
    assert not any(command[-1:] == [str(workspace / "node-sdk")] for command in commands)
    if name in runner.RECIPES:
        assert commands[0] == ["uv", "sync", "--locked", "--package", "notte-sdk", "--no-dev"]
        assert all(call["docs_python"] == str(workspace / ".venv/bin/python") for call in native)
    if name == "openai-agents":
        assert ["uv", "pip", "install", "openai-agents==0.24.0", "pytest", "pytest-timeout"] in commands
        assert ["uv", "run", "--no-sync", "pytest", "tests/sdk/test_websocket_compatibility.py", "-q"] in commands
    elif name == "claude-agents":
        assert ["uv", "pip", "install", "claude-agent-sdk==0.2.168"] in commands
        assert ["uv", "pip", "check"] in commands
    elif name == "agent-browser":
        assert len(native) == 3
        assert [
            "npm",
            "install",
            "--prefix",
            str(workspace / "runner-temp/notte-agent-browser"),
            "--no-audit",
            "--no-fund",
            "agent-browser@0.39.1",
        ] in commands
        assert native[1]["vitest"] == "" and native[2]["vitest"] == "1"
        assert all(call["journal"] == str(workspace / "runner-temp/agent-browser-owned.jsonl") for call in native)
    else:
        assert native[0]["live_flags"]["NOTTE_INNGEST_MODEL_LIVE"] == "1"


def test_github_actions_retains_flat_tests_and_selected_source_python(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped_project(workspace, monkeypatch, "github-actions", "NOTTE_EXAMPLE_PYTHON")
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["credentials"]]
    assert len(native) == 4
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in native)
    assert all(
        call["args"] == ["python", "-m", "unittest", "test_cli_signals", "test_live", "-v"] for call in native[::2]
    )
    assert native[0]["example_python"] == str(workspace / "examples/github-actions/.venv/bin/python")
    assert native[2]["example_python"] == str(workspace / ".venv/bin/python")
    commands = [call["args"] for call in observed]
    assert ["python", "-m", "unittest", "test_publish", "test_cli_signals", "-v"] in commands
    assert ["uv", "pip", "install", "--python", str(workspace / ".venv/bin/python"), "playwright==1.64.0"] in commands
    assert ["npm", "install", "--no-save", "--package-lock=false", str(workspace / "node-sdk")] in commands


@pytest.mark.parametrize("name,convention", [("trigger", "node-project"), ("openai-agents", "NOTTE_DOCS_PYTHON")])
def test_consolidated_native_failure_stops_before_other_sdk_or_project(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, convention: str
) -> None:
    shipped_project(workspace, monkeypatch, name, convention)
    monkeypatch.setenv("FAIL_NATIVE", "1")
    with pytest.raises(subprocess.CalledProcessError) as failure:
        runner.main()
    assert failure.value.returncode == 23
    observed = calls(workspace)
    assert (
        len(
            [
                call
                for call in observed
                if "test:live" in call["args"] or any(arg.endswith(".integration.test.ts") for arg in call["args"])
            ]
        )
        == 1
    )
    assert not any(call["args"][-1:] == [str(workspace / "node-sdk")] for call in observed)


def test_node_tag_is_limited_to_known_node_projects(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner.REGISTRY.write_text('{"alpha":"node-project"}')
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["alpha"]')
    with pytest.raises(ValueError, match="Unknown Node"):
        runner.projects("1/1")
    assert calls(workspace) == []


@pytest.mark.parametrize(
    "name,key",
    [("openai-agents", "OPENAI_API_KEY"), ("claude-agents", "ANTHROPIC_API_KEY"), ("inngest", "ANTHROPIC_API_KEY")],
)
def test_even_a_main_ref_pull_request_cannot_receive_paid_provider_credentials(name: str, key: str) -> None:
    env = {
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "pull_request",
        "NOTTE_API_KEY": "fixture-ci-key",  # pragma: allowlist secret
        key: "fixture-provider-key",
    }
    assert key not in runner.project_env(name, env)
    assert runner.project_env(name, env)["NOTTE_API_KEY"] == env["NOTTE_API_KEY"]


@pytest.mark.parametrize("name", ["inngest", "temporal", "trigger", "openai-agents"])
def test_existing_dependabot_eligibility_is_preserved(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    shipped_project(workspace, monkeypatch, name, "NOTTE_DOCS_PYTHON" if name == "openai-agents" else "node-project")
    monkeypatch.setenv("GITHUB_ACTOR", "dependabot[bot]")
    runner.main()
    assert bool(calls(workspace)) == (name in {"inngest", "temporal"})


def test_mongodb_live_owns_one_limited_fixture_and_original_source_suite(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped_project(workspace, monkeypatch, "mongodb", "NOTTE_DOCS_PYTHON")
    monkeypatch.setenv("MONGODB_URI", "mongodb://outside.invalid")
    runner.main()
    observed = calls(workspace)
    commands = [call["args"] for call in observed]
    docker = [call for call in observed if call["args"][0] == "docker"]
    assert [call["args"][1] for call in docker] == ["create", "start", "inspect", "rm"]
    create = docker[0]["args"]
    name = create[create.index("--name") + 1]
    assert name.startswith("notte-mongodb-") and len(name) == len("notte-mongodb-") + 32
    assert create[create.index("--publish") + 1] == "127.0.0.1:27017:27017"
    assert create[create.index("--memory") + 1] == "768m"
    assert create[create.index("--cpus") + 1] == "1"
    assert create[create.index("--health-cmd") + 1] == "mongosh --quiet --eval 'db.adminCommand({ ping: 1 }).ok'"
    for option, value in (("--health-interval", "5s"), ("--health-timeout", "5s"), ("--health-retries", "20")):
        assert create[create.index(option) + 1] == value
    assert create[-1] == "mongo:8.0@sha256:6657bf2413fefc5be649390318f5b4cd7328e982722f8ce2ac6dfa6f0a42cb03"
    assert all(call["args"][-1] == name for call in docker[1:])
    assert docker[-1]["args"] == ["docker", "rm", "--force", "--volumes", name]
    assert all(not call["credentials"] for call in docker)
    native = [call for call in observed if "vitest" in call["args"]]
    assert len(native) == 1
    assert native[0]["args"] == ["npx", "vitest", "run", "test/mongodb.integration.test.ts"]
    assert native[0]["mongodb_uri"] == "mongodb://127.0.0.1:27017"
    assert native[0]["docs_python"] == str(workspace / ".venv/bin/python")
    assert native[0]["live_flags"]["NOTTE_MONGODB_LIVE"] == "1"
    assert native[0]["credentials"] == ["NOTTE_API_KEY"]
    assert ["uv", "pip", "install", "pymongo==4.19.0"] in commands
    assert ["uv", "pip", "check"] in commands
    assert commands.index(docker[2]["args"]) < commands.index(native[0]["args"]) < commands.index(docker[3]["args"])


def test_mongodb_static_and_unselected_shard_never_start_docker(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped_project(workspace, monkeypatch, "mongodb", "NOTTE_DOCS_PYTHON")
    monkeypatch.setattr("sys.argv", ["runner", "checks"])
    runner.main()
    monkeypatch.setattr("sys.argv", ["runner", "live", "--shard", "2/2"])
    runner.main()
    assert calls(workspace) == []


@pytest.mark.parametrize("failure", ["create", "start", "inspect", "unhealthy", "timeout", "native", "rm"])
def test_mongodb_fixture_failure_propagates_and_cleans_only_owned_container(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    shipped_project(workspace, monkeypatch, "mongodb", "NOTTE_DOCS_PYTHON")
    if failure in {"create", "start", "inspect", "rm"}:
        monkeypatch.setenv("FAIL_DOCKER", failure)
    elif failure == "unhealthy":
        monkeypatch.setenv("MONGO_HEALTH", "unhealthy")
    elif failure == "timeout":
        times = iter([0, 121])
        monkeypatch.setattr(runner.time, "monotonic", lambda: next(times))
    else:
        monkeypatch.setenv("FAIL_NATIVE", "1")
    with pytest.raises((subprocess.CalledProcessError, RuntimeError, TimeoutError)) as result:
        runner.main()
    docker = [call["args"] for call in calls(workspace) if call["args"][0] == "docker"]
    if failure == "create":
        assert len(docker) == 1
    else:
        assert docker[-1] == ["docker", "rm", "--force", "--volumes", docker[0][docker[0].index("--name") + 1]]
    native = [call for call in calls(workspace) if "vitest" in call["args"]]
    assert len(native) == (1 if failure in {"native", "rm"} else 0)
    if failure == "native":
        assert isinstance(result.value, subprocess.CalledProcessError) and result.value.returncode == 23


def test_mongodb_cleanup_failure_keeps_original_native_failure(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped_project(workspace, monkeypatch, "mongodb", "NOTTE_DOCS_PYTHON")
    monkeypatch.setenv("FAIL_NATIVE", "1")
    monkeypatch.setenv("FAIL_DOCKER", "rm")
    with pytest.raises(subprocess.CalledProcessError) as failure:
        runner.main()
    assert failure.value.returncode == 23
    assert "Failed to remove owned MongoDB fixture" in failure.value.__notes__


@pytest.mark.parametrize("failure", [False, True])
def test_onepassword_ts_driver_preserves_validation_modes_and_no_vault_dependency(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    runner.REGISTRY.write_text(json.dumps({"onepassword": "typescript-driver"}))  # pragma: allowlist secret
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["onepassword"]')
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "fixture-unused-token")
    project = workspace / "examples/onepassword"
    (project / "typescript").mkdir(parents=True)
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
    python.chmod(0o755)
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    if failure:
        monkeypatch.setenv("FAIL_TS_DRIVER", "1")
        with pytest.raises(subprocess.CalledProcessError) as error:
            runner.main()
        assert error.value.returncode == 19
    else:
        runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["args"] == ["npm", "run", "test:live"]]
    assert len(native) == (1 if failure else 2)
    assert all(call["onepassword_python"] == str(python) for call in native)
    assert all(call["cwd"] == str(project / "typescript") for call in native)
    assert all(not call["credentials"] for call in observed if call not in native)
    assert not any("unittest" in call["args"] for call in observed)
    commands = [call["args"] for call in observed]
    assert [
        "python",
        "-c",
        'from onepassword import Secrets; from notte_sdk import NotteClient; Secrets.validate_secret_reference("op://Test/Login/username")',
    ] in commands
    overlays = [command for command in commands if command[:3] == ["uv", "pip", "install"]]
    if failure:
        assert not overlays
    else:
        assert len(overlays) == 1 and "--no-deps" not in overlays[0]
        assert commands.index(overlays[0]) > commands.index(native[0]["args"])
