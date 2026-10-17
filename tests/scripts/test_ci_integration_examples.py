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
        'credentials': sorted(k for k in ('NOTTE_API_KEY', 'OPENAI_API_KEY', 'BRAINTRUST_API_KEY', 'LMNR_PROJECT_API_KEY', 'OP_SERVICE_ACCOUNT_TOKEN') if os.environ.get(k)),
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
if args[1:] == ['install_driver.py']:
    print(os.environ['DRIVER_OUTPUT'])
    print('Driver setup diagnostic', file=sys.stderr)
    if os.environ.get('FAIL_DRIVER'):
        sys.exit(17)
if os.environ.get('FAIL_UNITTEST') and 'unittest' in args:
    sys.exit(19)
if os.environ.get('FAIL_TS_DRIVER') and args == ['npm', 'run', 'test:live']:
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
