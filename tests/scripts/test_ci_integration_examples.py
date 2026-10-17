"""Exercise native runner isolation, SDK resolution, sharding, and failure propagation."""

import hashlib
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
        'credentials': sorted(k for k in ('AGENTCARD_CLIENT_ID', 'AGENTCARD_CLIENT_SECRET', 'ANTHROPIC_API_KEY', 'BOX_ACCESS_TOKEN', 'BRAINTRUST_API_KEY', 'GEMINI_API_KEY', 'LINK_ACCESS_TOKEN', 'LINK_SPEND_REQUEST_ID', 'LMNR_PROJECT_API_KEY', 'NOTTE_API_KEY', 'NOTTE_VALTOWN_TOKEN', 'OPENAI_API_KEY', 'OP_SERVICE_ACCOUNT_TOKEN', 'WATSONX_API_KEY', 'WATSONX_PROJECT_ID', 'WATSONX_MODEL_ID', 'WATSONX_URL') if os.environ.get(k)),
        'vitest': os.environ.get('VITEST_INTEGRATION'),
        'journal': os.environ.get('NOTTE_AGENT_BROWSER_OWNERSHIP_JOURNAL'),
        'example_python': os.environ.get('NOTTE_EXAMPLE_PYTHON'),
        'docs_python': os.environ.get('NOTTE_DOCS_PYTHON'),
        'python': os.environ.get('NOTTE_COMPUTER_USE_PYTHON'),
        'braintrust_python': os.environ.get('NOTTE_BRAINTRUST_PYTHON'),
        'braintrust_project': os.environ.get('BRAINTRUST_PROJECT'),
        'link_python': os.environ.get('NOTTE_LINK_PYTHON'),
        'link_required': os.environ.get('NOTTE_LINK_REQUIRE_LIVE'),
        'watsonx_python': os.environ.get('NOTTE_WATSONX_PYTHON'),
        'watsonx_required': os.environ.get('NOTTE_WATSONX_REQUIRE_LIVE'),
        'onepassword_python': os.environ.get('NOTTE_ONEPASSWORD_PYTHON'),
        'gemini_live': os.environ.get('NOTTE_GEMINI_LIVE'),
        'gemini_model': os.environ.get('NOTTE_GEMINI_MODEL_LIVE'),
        'selenium_live': os.environ.get('NOTTE_SELENIUM_LIVE'),
        'live_flags': {k: v for k, v in os.environ.items() if k.startswith('NOTTE_') and k.endswith('_LIVE')},
        'tracing': os.environ.get('LANGSMITH_TRACING'),
        'driver': os.environ.get('CHROMEDRIVER_PATH')}) + '\\n')
if args[0] == 'curl':
    Path(args[-1]).write_bytes(b'owned-sbx-archive')
if os.environ.get('FAIL_CLI_CONTRACT') and 'check-cli.mjs' in args:
    sys.exit(41)
if os.environ.get('FAIL_DENO') == 'static' and 'fmt' in args:
    sys.exit(37)
if os.environ.get('FAIL_DENO') == 'live' and 'test:live' in args:
    sys.exit(37)
if args[1:] == ['install_driver.py']:
    print(os.environ['DRIVER_OUTPUT'])
    print('Driver setup diagnostic', file=sys.stderr)
    if os.environ.get('FAIL_DRIVER'):
        sys.exit(17)
if os.environ.get('FAIL_BOX_CAPTURE') == 'python' and 'test_capture' in args:
    sys.exit(29)
if os.environ.get('FAIL_BOX_CAPTURE') == 'typescript' and 'test:capture' in args:
    sys.exit(29)
if os.environ.get('FAIL_UNITTEST') and 'unittest' in args:
    sys.exit(19)
if os.environ.get('FAIL_TS_DRIVER') and args == ['npm', 'run', 'test:live']:
    sys.exit(19)
if os.environ.get('FAIL_NATIVE') and ('test:live' in args or any(arg.endswith('.integration.test.ts') for arg in args)):
    sys.exit(23)
"""
    for path in (
        tmp_path / "bin/uv",
        tmp_path / "bin/npm",
        tmp_path / "bin/npx",
        tmp_path / "bin/curl",
        tmp_path / "bin/tar",
        tmp_path / "bin/sh",
        tmp_path / "bin/node",
    ):
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


@pytest.fixture
def box_project(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runner.REGISTRY.write_text('{"box":"box-root"}')
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["box"]')
    project = workspace / "examples/box"
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
    python.chmod(0o755)
    return project


def test_box_preserves_root_static_capture_suites_and_credential_boundaries(
    workspace: Path, box_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-private-provider")
    monkeypatch.setenv("NOTTE_BOX_CAPTURE_LIVE", "1")
    monkeypatch.setenv("NOTTE_BOX_LIVE", "1")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    runner.main()
    observed = calls(workspace)
    static = [call for call in observed if "test_upload" in call["args"] or call["args"] == ["npm", "test"]]
    native = [call for call in observed if "test_capture" in call["args"] or "test:capture" in call["args"]]
    assert len(static) == 2 and len(native) == 4
    assert all(call["cwd"] == str(box_project) for call in static + native)
    assert all(not call["credentials"] and call["live_flags"]["NOTTE_BOX_CAPTURE_LIVE"] == "0" for call in static)
    assert all(
        call["credentials"] == ["NOTTE_API_KEY"] and call["live_flags"]["NOTTE_BOX_CAPTURE_LIVE"] == "1"
        for call in native
    )
    assert all(call["live_flags"]["NOTTE_BOX_LIVE"] == "0" for call in static + native)
    assert all(not call["credentials"] for call in observed if call not in native)
    commands = [call["args"] for call in observed]
    assert commands[0] == ["uv", "venv", str(box_project / ".venv"), "--clear", "--python", "3.12"]
    assert [
        "python",
        "-m",
        "compileall",
        "-q",
        "main.py",
        "cleanup_case.py",
        "test_box.py",
        "test_capture.py",
    ] in commands
    assert [
        "uv",
        "pip",
        "install",
        "--python",
        str(box_project / ".venv/bin/python"),
        "-r",
        "requirements.txt",
    ] in commands
    assert commands.count(["uv", "pip", "check", "--python", str(box_project / ".venv/bin/python")]) == 2
    assert commands.count(["npm", "run", "typecheck"]) == 2
    source = next(command for command in commands if "-e" in command)
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert "--no-deps" not in source
    assert commands.index(source) > commands.index(native[1]["args"])
    assert ["npm", "install", "--no-save", "--package-lock=false", str(workspace / "node-sdk")] in commands
    assert not any("test_box" in command or "test:live" in command for command in commands)


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_box_capture_failure_reaches_paired_gate_before_source_or_other_project(
    workspace: Path, box_project: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    monkeypatch.setenv("FAIL_BOX_CAPTURE", language)
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    with pytest.raises(subprocess.CalledProcessError) as failure:
        runner.main()
    assert failure.value.returncode == 29
    assert not any("-e" in call["args"] for call in calls(workspace))
    assert all(
        not call["credentials"]
        for call in calls(workspace)
        if "test_capture" not in call["args"] and "test:capture" not in call["args"]
    )


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


@pytest.mark.parametrize(
    "name,count", [("agentcard", 2), ("trigger", 2), ("inngest", 1), ("replit", 1), ("temporal", 1)]
)
def test_node_projects_keep_existing_sdk_modes_and_no_paid_pr_calls(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, count: int
) -> None:
    project = shipped_project(workspace, monkeypatch, name, "node-project")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-unused-provider")
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["args"] == ["npm", "run", "test:live"]]
    assert len(native) == count
    assert all(call["credentials"] == ["NOTTE_API_KEY"] and call["cwd"] == str(project) for call in native)
    if name != "replit":
        assert all(call["live_flags"][f"NOTTE_{name.upper()}_LIVE"] == "1" for call in native)
    assert all(not call["credentials"] for call in observed if call not in native)
    commands = [call["args"] for call in observed]
    source = [command for command in commands if command[:2] == ["npm", "install"]]
    assert len(source) == count - 1
    if source:
        assert source[0] == ["npm", "install", "--no-save", "--package-lock=false", str(workspace / "node-sdk")]
        assert commands.count(["npm", "test"]) == 3
        assert commands.count(["npm", "run", "typecheck"]) == 3
    if name == "replit":
        assert commands == [["npm", "ci"], ["npm", "test"], ["npm", "run", "test:live"]]
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


@pytest.mark.parametrize(
    "name,convention",
    [
        ("agentcard", "node-project"),
        ("replit", "node-project"),
        ("trigger", "node-project"),
        ("openai-agents", "NOTTE_DOCS_PYTHON"),
    ],
)
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


@pytest.mark.parametrize("name", ["inngest", "temporal", "trigger", "replit", "openai-agents"])
def test_existing_dependabot_eligibility_is_preserved(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    shipped_project(workspace, monkeypatch, name, "NOTTE_DOCS_PYTHON" if name == "openai-agents" else "node-project")
    monkeypatch.setenv("GITHUB_ACTOR", "dependabot[bot]")
    runner.main()
    assert bool(calls(workspace)) == (name in {"inngest", "temporal"})


def test_replit_output_names_hosted_mcp_without_sdk_claims(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shipped_project(workspace, monkeypatch, "replit", "node-project")
    runner.main()
    output = capsys.readouterr().out
    assert "Native integration: replit, hosted MCP" in output
    assert "published" not in output and "source SDK" not in output


@pytest.fixture
def docker_project(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shipped_project(workspace, monkeypatch, "docker-sandboxes", "node-project")
    monkeypatch.setattr(runner, "DOCKER_CLI_SHA256", hashlib.sha256(b"owned-sbx-archive").hexdigest())
    return workspace / "examples/docker-sandboxes"


def test_docker_preserves_checksum_cli_help_and_single_hosted_mcp_owner(
    workspace: Path, docker_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-private-provider")
    monkeypatch.setenv("NOTTE_SANDBOXES_LIVE", "1")
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if "test:live" in call["args"]]
    assert len(native) == 1 and native[0]["credentials"] == ["NOTTE_API_KEY"]
    assert native[0]["live_flags"]["NOTTE_SANDBOXES_LIVE"] == "1"
    assert all(not call["credentials"] for call in observed if call not in native)
    assert all(call["live_flags"]["NOTTE_SANDBOXES_LIVE"] == "0" for call in observed if call not in native)
    commands = [call["args"] for call in observed]
    prefix = workspace / "runner-temp/notte-docker-sandboxes-cli"
    assert commands == [
        ["npm", "ci"],
        ["npm", "run", "typecheck"],
        ["npm", "test"],
        ["sh", "-n", "setup.sh"],
        [
            "curl",
            "-fsSL",
            "https://github.com/docker/sbx-releases/releases/download/v0.48.0/DockerSandboxes-linux-amd64.tar.gz",
            "-o",
            str(prefix / "sbx.tar.gz"),
        ],
        ["tar", "-xzf", str(prefix / "sbx.tar.gz"), "-C", str(prefix)],
        ["node", "check-cli.mjs", str(prefix / "docker-sbx/sbx")],
        ["npm", "run", "test:live"],
    ]
    assert all(call["cwd"] == str(docker_project) for call in observed)


def test_docker_bad_checksum_never_extracts_or_runs_cli_or_native_suite(
    workspace: Path, docker_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "DOCKER_CLI_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.main()
    assert calls(workspace)[-1]["args"][0] == "curl"
    assert not any(
        call["args"][0] == "tar" or "check-cli.mjs" in call["args"] or "test:live" in call["args"]
        for call in calls(workspace)
    )


@pytest.mark.parametrize("failure", ["cli", "native"])
def test_docker_cli_or_mcp_failure_fails_existing_paired_owner(
    workspace: Path, docker_project: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setenv("FAIL_CLI_CONTRACT" if failure == "cli" else "FAIL_NATIVE", "1")
    with pytest.raises(subprocess.CalledProcessError) as error:
        runner.main()
    assert error.value.returncode == (41 if failure == "cli" else 23)
    assert len([call for call in calls(workspace) if "test:live" in call["args"]]) == (failure == "native")


@pytest.fixture
def stripe_link_project(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runner.REGISTRY.write_text('{"stripe-link":"typescript-driver"}')
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["stripe-link"]')
    project = workspace / "examples/stripe-link"
    (project / "typescript").mkdir(parents=True)
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
    python.chmod(0o755)
    return project


def test_stripe_link_retains_native_driver_alias_offline_tests_and_wallet_boundary(
    workspace: Path, stripe_link_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-private-provider")
    monkeypatch.setenv("NOTTE_LINK_REQUIRE_LIVE", "1")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if "test:live" in call["args"]]
    static = [call for call in observed if "unittest" in call["args"] or call["args"] == ["npm", "test"]]
    assert len(native) == 2 and len(static) == 2
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in native)
    assert all(
        call["link_required"] == "1" and call["link_python"] == str(stripe_link_project / ".venv/bin/python")
        for call in native
    )
    assert all(not call["credentials"] and call["link_required"] == "0" for call in static)
    assert all(not call["credentials"] for call in observed if call not in native)
    assert all(call["cwd"] == str(stripe_link_project / "typescript") for call in native)
    commands = [call["args"] for call in observed]
    assert ["python", "-c", "from link import AsyncClient; from notte_sdk import NotteClient"] in commands
    assert ["python", "-m", "unittest", "discover", "-s", "python"] in commands
    assert ["npm", "test"] in commands
    source = next(command for command in commands if "-e" in command)
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert "--no-deps" not in source
    assert commands.index(source) > commands.index(native[0]["args"])
    assert commands.count(["npm", "run", "typecheck"]) == 2
    assert ["npm", "install", "--no-save", "--package-lock=false", str(workspace / "node-sdk")] in commands


def test_stripe_link_native_driver_failure_reaches_paired_gate_before_source(
    workspace: Path, stripe_link_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAIL_TS_DRIVER", "1")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    with pytest.raises(subprocess.CalledProcessError) as failure:
        runner.main()
    assert failure.value.returncode == 19
    assert not any("-e" in call["args"] for call in calls(workspace))


@pytest.fixture
def valtown_project(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runner.REGISTRY.write_text('{"valtown":"valtown-deno"}')
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["valtown"]')
    monkeypatch.setenv("RUNNER_TEMP", str(workspace / "runner-temp"))
    cli = workspace / "runner-temp/notte-valtown-deno/node_modules/.bin/deno"
    cli.parent.mkdir(parents=True)
    cli.write_text((workspace / "examples/alpha/.venv/bin/python").read_text())
    cli.chmod(0o755)
    project = workspace / "examples/valtown"
    project.mkdir(parents=True)
    return project


def test_valtown_installs_without_credentials_and_runs_one_native_fetch_suite(
    workspace: Path, valtown_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-private-provider")
    monkeypatch.setenv("NOTTE_VALTOWN_LIVE", "1")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    runner.main()
    observed = calls(workspace)
    commands = [call["args"] for call in observed]
    native = [call for call in observed if "test:live" in call["args"]]
    assert len(native) == 1
    assert commands[0] == [
        "npm",
        "install",
        "--prefix",
        str(workspace / "runner-temp/notte-valtown-deno"),
        "--no-audit",
        "--no-fund",
        "deno@2.9.6",
    ]
    assert [command[1:] for command in commands[1:]] == [
        ["fmt", "--check", "main.ts", "main_test.ts", "deno.json"],
        ["lint", "main.ts", "main_test.ts"],
        ["task", "check"],
        ["task", "test"],
        ["task", "test:live"],
    ]
    assert all(call["credentials"] == [] and call["live_flags"]["NOTTE_VALTOWN_LIVE"] == "0" for call in observed[:-1])
    assert native[0]["credentials"] == ["NOTTE_API_KEY"]
    assert native[0]["live_flags"]["NOTTE_VALTOWN_LIVE"] == "1"
    assert all(call["cwd"] == str(valtown_project) for call in observed)
    assert not any("uv" in command or "npx" in command for command in commands)
    assert not any("--allow-net" in command for command in commands)
    assert not any("-e" in command for command in commands)


def test_valtown_unselected_shard_does_no_setup(
    workspace: Path, valtown_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["runner", "live", "--shard", "2/2"])
    runner.main()
    assert calls(workspace) == []


@pytest.mark.parametrize("phase", ["static", "live"])
def test_valtown_cli_failure_stops_existing_paired_owner(
    workspace: Path, valtown_project: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    monkeypatch.setenv("FAIL_DENO", phase)
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    with pytest.raises(subprocess.CalledProcessError) as failure:
        runner.main()
    assert failure.value.returncode == 37
    assert len([call for call in calls(workspace) if "test:live" in call["args"]]) == (phase == "live")


def test_valtown_default_tests_cannot_use_network_permission() -> None:
    config = json.loads((Path(__file__).parents[2] / "examples/valtown/deno.json").read_text())
    assert config["tasks"] == {
        "check": "deno check main.ts main_test.ts",
        "test": "deno test --allow-env main_test.ts",
        "test:live": "deno test --allow-env --allow-net main_test.ts",
    }


@pytest.fixture
def watsonx_project(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = shipped_project(workspace, monkeypatch, "watsonx", "typescript-driver")
    (project / "typescript").mkdir()
    return project


def test_watsonx_preserves_offline_native_driver_and_ibm_isolation(
    workspace: Path, watsonx_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-private-provider")
    monkeypatch.setenv("NOTTE_WATSONX_REQUIRE_LIVE", "1")
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if "test:live" in call["args"]]
    static = [call for call in observed if "unittest" in call["args"] or call["args"] == ["npm", "test"]]
    assert len(native) == 2 and len(static) == 2
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in native)
    assert all(
        call["watsonx_required"] == "1" and call["watsonx_python"] == str(watsonx_project / ".venv/bin/python")
        for call in native
    )
    assert all(not call["credentials"] for call in observed if call not in native)
    assert all(call["watsonx_required"] == "0" for call in static)
    commands = [call["args"] for call in observed]
    assert ["python", "-c", "import requests; from notte_sdk import NotteClient"] in commands
    assert ["python", "-m", "unittest", "discover", "-s", "python"] in commands
    assert ["npm", "test"] in commands
    source = next(command for command in commands if "-e" in command)
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert "--no-deps" not in source
    assert commands.index(source) > commands.index(native[0]["args"])
    assert commands.count(["npm", "run", "typecheck"]) == 2


def test_watsonx_native_failure_reaches_existing_paired_owner_before_source(
    workspace: Path, watsonx_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAIL_TS_DRIVER", "1")
    with pytest.raises(subprocess.CalledProcessError) as error:
        runner.main()
    assert error.value.returncode == 19
    assert not any("-e" in call["args"] for call in calls(workspace))
