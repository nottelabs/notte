"""Exercise native runner isolation, SDK resolution, sharding, and failure propagation."""

import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
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
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-router-key")
    monkeypatch.delenv("BRAINTRUST_API_KEY", raising=False)
    # CI sets this to dependabot[bot] on Dependabot PRs, which narrows the live phase to inngest and temporal.
    monkeypatch.delenv("GITHUB_ACTOR", raising=False)
    stub = """#!/usr/bin/env python3
import json, os, sys
import zipfile
from pathlib import Path

args = [Path(sys.argv[0]).name, *sys.argv[1:]]
with open(os.environ["COMMAND_LOG"], "a") as log:
    log.write(
        json.dumps(
            {
                "args": args,
                "cwd": os.getcwd(),
                "loop_patch": os.environ.get("NOTTE_ENABLE_NEST_ASYNCIO"),
                "credentials": sorted(
                    (
                        k
                        for k in (
                            "AGENTCARD_CLIENT_ID",
                            "AGENTCARD_CLIENT_SECRET",
                            "AI_GATEWAY_API_KEY",
                            "ANTHROPIC_API_KEY",
                            "ANTHROPIC_AUTH_TOKEN",
                            "BOX_ACCESS_TOKEN",
                            "BRAINTRUST_API_KEY",
                            "GEMINI_API_KEY",
                            "LINK_ACCESS_TOKEN",
                            "LINK_SPEND_REQUEST_ID",
                            "LMNR_PROJECT_API_KEY",
                            "MONGODB_URI",
                            "NOTTE_API_KEY",
                            "NOTTE_VALTOWN_TOKEN",
                            "OAGI_API_KEY",
                            "OPENAI_API_KEY",
                            "OPENROUTER_API_KEY",
                            "OP_SERVICE_ACCOUNT_TOKEN",
                            "PIPEDREAM_ACTION_FILE",
                            "PIPEDREAM_APP",
                            "PIPEDREAM_CLIENT_ID",
                            "PIPEDREAM_CLIENT_SECRET",
                            "PIPEDREAM_EXTERNAL_USER_ID",
                            "PIPEDREAM_PROJECT_ID",
                            "TZAFON_API_KEY",
                            "WATSONX_API_KEY",
                            "WATSONX_MODEL_ID",
                            "WATSONX_PROJECT_ID",
                            "WATSONX_URL",
                            "YUTORI_API_KEY",
                        )
                        if os.environ.get(k)
                    )
                ),
                "vitest": os.environ.get("VITEST_INTEGRATION"),
                "journal": os.environ.get("NOTTE_AGENT_BROWSER_OWNERSHIP_JOURNAL"),
                "example_python": os.environ.get("NOTTE_EXAMPLE_PYTHON"),
                "docs_python": os.environ.get("NOTTE_DOCS_PYTHON"),
                "python": os.environ.get("NOTTE_COMPUTER_USE_PYTHON"),
                "braintrust_python": os.environ.get("NOTTE_BRAINTRUST_PYTHON"),
                "braintrust_project": os.environ.get("BRAINTRUST_PROJECT"),
                "link_python": os.environ.get("NOTTE_LINK_PYTHON"),
                "link_required": os.environ.get("NOTTE_LINK_REQUIRE_LIVE"),
                "watsonx_python": os.environ.get("NOTTE_WATSONX_PYTHON"),
                "watsonx_required": os.environ.get("NOTTE_WATSONX_REQUIRE_LIVE"),
                "tzafon_python": os.environ.get("NOTTE_TZAFON_PYTHON"),
                "tzafon_required": os.environ.get("NOTTE_TZAFON_REQUIRE_LIVE"),
                "onepassword_python": os.environ.get("NOTTE_ONEPASSWORD_PYTHON"),
                "gemini_live": os.environ.get("NOTTE_GEMINI_LIVE"),
                "gemini_model": os.environ.get("NOTTE_GEMINI_MODEL_LIVE"),
                "selenium_live": os.environ.get("NOTTE_SELENIUM_LIVE"),
                "live_flags": {k: v for k, v in os.environ.items() if k.startswith("NOTTE_") and k.endswith("_LIVE")},
                "tracing": os.environ.get("LANGSMITH_TRACING"),
                "driver": os.environ.get("CHROMEDRIVER_PATH"),
                "e2e_telemetry": os.environ.get("E2E_TELEMETRY_DISABLED"),
                "mongodb_uri": os.environ.get("MONGODB_URI"),
            }
        )
        + "\\n"
    )
if args[0] == "curl":
    if "terraform" in args[2]:
        with zipfile.ZipFile(args[-1], "w") as archive:
            archive.writestr(zipfile.ZipInfo("terraform"), b"fixture Terraform CLI")
    else:
        Path(args[-1]).write_bytes(b"owned-sbx-archive")
if os.environ.get("FAIL_CLI_CONTRACT") and "check-cli.mjs" in args:
    sys.exit(41)
if os.environ.get("FAIL_DENO") == "static" and "fmt" in args:
    sys.exit(37)
if os.environ.get("FAIL_DENO") == "live" and "test:live" in args:
    sys.exit(37)
if args[1:] == ["install_driver.py"]:
    print(os.environ["DRIVER_OUTPUT"])
    print("Driver setup diagnostic", file=sys.stderr)
    if os.environ.get("FAIL_DRIVER"):
        sys.exit(17)
if os.environ.get("FAIL_BOX_CAPTURE") == "python" and "test_capture" in args:
    sys.exit(29)
if os.environ.get("FAIL_BOX_CAPTURE") == "typescript" and "test:capture" in args:
    sys.exit(29)
if os.environ.get("FAIL_UNITTEST") and "unittest" in args:
    sys.exit(19)
if os.environ.get("FAIL_TS_DRIVER") and args == ["npm", "run", "test:live"]:
    sys.exit(19)
if os.environ.get("FAIL_NATIVE") and (
    "test:live" in args or any((arg.endswith(".integration.test.ts") for arg in args))
):
    sys.exit(23)
if os.environ.get("FAIL_PIPEDREAM_IMPORT") and args[1:] == ["-c", "import demo"]:
    sys.exit(31)
if os.environ.get("FAIL_PIPEDREAM_NODE") and args == ["npm", "test"]:
    sys.exit(23)
if os.environ.get("FAIL_OPENAGI_IMPORT") and args[1:] == ["-c", "import demo; from oagi import AsyncDefaultAgent"]:
    sys.exit(31)
if os.environ.get("FAIL_PRIME_NATIVE") and "unittest" in args and (os.environ.get("NOTTE_PRIME_LIVE") == "1"):
    sys.exit(19)
if args[0] == "uv" and args[1] == "venv":
    python = Path(args[2]) / "bin/python"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text(Path(sys.argv[0]).read_text())
    python.chmod(493)
if os.environ.get("FAIL_TERRAFORM_LIVE") and args[:3] == ["go", "test", "-count=1"]:
    sys.exit(31)
if os.environ.get("FAIL_NATIVE") and (
    "test:live" in args
    or any((arg.endswith(".integration.test.ts") for arg in args))
    or (args == ["npm", "test"] and any((os.environ.get(key) == "1" for key in ("NOTTE_EVE_LIVE", "NOTTE_FX_LIVE"))))
):
    sys.exit(23)
if args[0] == "docker":
    if os.environ.get("FAIL_DOCKER") == args[1]:
        sys.exit(31)
    if args[1] == "inspect":
        print(os.environ.get("MONGO_HEALTH", "healthy"))
if args[0] == "vitest":
    report = next(arg.split("=", 1)[1] for arg in args if arg.startswith("--outputFile="))
    Path(report).write_text(json.dumps({
        "numTotalTests": int(os.environ.get("AGENT_TOTAL", "6")), "numPendingTests": int(os.environ.get("AGENT_PENDING", "0")),
        "numTodoTests": 0, "numFailedTests": 0,
    }))
"""
    assert stub.startswith("#!/usr/bin/env python3\n")
    for path in (
        tmp_path / "bin/uv",
        tmp_path / "bin/npm",
        tmp_path / "bin/npx",
        tmp_path / "bin/curl",
        tmp_path / "bin/tar",
        tmp_path / "bin/sh",
        tmp_path / "bin/node",
        tmp_path / "bin/go",
        tmp_path / "bin/docker",
        tmp_path / "node-sdk/node_modules/.bin/vitest",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stub)
        path.chmod(493)
    for name in ("alpha", "beta", "gamma"):
        project = tmp_path / "examples" / name
        (project / "typescript").mkdir(parents=True)
        python = project / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text(stub)
        python.chmod(493)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{Path(sys.executable).parent}")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner-temp"))
    return tmp_path


def agent_phases(monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as prepare:
        for key in runner.CREDENTIALS:
            prepare.delenv(key, raising=False)
        prepare.setattr("sys.argv", ["runner", "prepare-agent"])
        runner.main()
    with monkeypatch.context() as execute:
        execute.setattr("sys.argv", ["runner", "test-agent"])
        runner.main()


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
    monkeypatch.setenv("NOTTE_ENABLE_NEST_ASYNCIO", "true")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    runner.main()
    observed = calls(workspace)
    assert all(call["loop_patch"] == "false" for call in observed)
    tests = [call for call in observed if "unittest" in call["args"] or "test:live" in call["args"]]
    assert len(tests) == 4
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in tests)
    assert all(call["python"] == str(workspace / "examples/alpha/.venv/bin/python") for call in tests)
    assert all(not call["credentials"] for call in observed if call not in tests)
    commands = [call["args"] for call in observed]
    assert commands[0] == ["uv", "sync", "--locked"]
    source = next(command for command in commands if command[:3] == ["uv", "pip", "install"])
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert "--no-deps" not in source
    assert ["npm", "install", "--no-save", str(workspace / "node-sdk")] in commands
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
    assert ["npm", "install", "--no-save", str(workspace / "node-sdk")] in commands
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
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("ANTHROPIC_API_KEY" if name == "deepagents" else "LMNR_PROJECT_API_KEY", "fixture-own-provider")
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
        assert source[0] == ["npm", "install", "--no-save", str(workspace / "node-sdk")]
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
    if name in runner.AGENT_RECIPES:
        agent_phases(monkeypatch)
    else:
        runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["credentials"]]
    expected = sorted(["NOTTE_API_KEY", provider]) if provider else ["NOTTE_API_KEY"]
    if name == "openai-agents":
        expected = ["NOTTE_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"]
    elif name == "claude-agents":
        expected = ["ANTHROPIC_AUTH_TOKEN", "NOTTE_API_KEY", "OPENROUTER_API_KEY"]
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
    assert ["npm", "install", "--no-save", str(workspace / "node-sdk")] in commands


@pytest.mark.parametrize("name,convention", [("trigger", "node-project"), ("openai-agents", "NOTTE_DOCS_PYTHON")])
def test_consolidated_native_failure_stops_before_other_sdk_or_project(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, convention: str
) -> None:
    shipped_project(workspace, monkeypatch, name, convention)
    monkeypatch.setenv("FAIL_NATIVE", "1")
    with pytest.raises(subprocess.CalledProcessError) as failure:
        if name in runner.AGENT_RECIPES:
            agent_phases(monkeypatch)
        else:
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


@pytest.mark.parametrize("failure", [False, True])
def test_braintrust_ts_driver_preserves_python_selection_and_credential_isolation(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
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
    assert all(call["credentials"] == ["BRAINTRUST_API_KEY", "NOTTE_API_KEY"] for call in native)
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
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
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
    assert ["npm", "install", "--no-save", str(workspace / "node-sdk")] in commands
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
    assert ["python", "-c", "from link import AsyncClient; from notte_sdk import AsyncNotteClient"] in commands
    assert ["python", "-m", "unittest", "discover", "-s", "python"] in commands
    assert ["npm", "test"] in commands
    source = next(command for command in commands if "-e" in command)
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert "--no-deps" not in source
    assert commands.index(source) > commands.index(native[0]["args"])
    assert commands.count(["npm", "run", "typecheck"]) == 2
    assert ["npm", "install", "--no-save", str(workspace / "node-sdk")] in commands


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


@pytest.fixture
def tzafon_project(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = shipped_project(workspace, monkeypatch, "tzafon", "typescript-driver")
    (project / "typescript").mkdir()
    return project


def test_tzafon_preserves_native_driver_and_excludes_model_credentials(
    workspace: Path, tzafon_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-private-provider")
    monkeypatch.setenv("NOTTE_TZAFON_REQUIRE_LIVE", "1")
    runner.main()
    observed = calls(workspace)
    native = [call for call in observed if "test:live" in call["args"]]
    static = [call for call in observed if "unittest" in call["args"] or call["args"] == ["npm", "test"]]
    assert len(native) == 2 and len(static) == 2
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in native)
    assert all(
        call["tzafon_required"] == "1" and call["tzafon_python"] == str(tzafon_project / ".venv/bin/python")
        for call in native
    )
    assert all(not call["credentials"] for call in observed if call not in native)
    assert all(call["tzafon_required"] == "0" for call in static)
    commands = [call["args"] for call in observed]
    assert ["python", "-c", "from tzafon import AsyncLightcone; from notte_sdk import NotteClient"] in commands
    assert ["python", "-m", "unittest", "discover", "-s", "python"] in commands
    assert ["npm", "test"] in commands
    source = next(command for command in commands if "-e" in command)
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert "--no-deps" not in source
    assert commands.index(source) > commands.index(native[0]["args"])
    assert commands.count(["npm", "run", "typecheck"]) == 2


def test_tzafon_native_failure_fails_paired_owner_before_source(
    workspace: Path, tzafon_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAIL_TS_DRIVER", "1")
    with pytest.raises(subprocess.CalledProcessError) as error:
        runner.main()
    assert error.value.returncode == 19
    assert not any("-e" in call["args"] for call in calls(workspace))


@pytest.mark.parametrize("fail", [None, "static", "live"])
def test_prime_preserves_python_modes_without_node_or_paid_credentials(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, fail: str | None
) -> None:
    project = shipped_project(workspace, monkeypatch, "prime-intellect", "python-project")
    (project / "test_notte_prime.py").write_text("# Test module fixture\n")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("NOTTE_PRIME_LIVE", "1")
    for credential in runner.CREDENTIALS:
        monkeypatch.setenv(credential, "fixture-private-value")
    if fail:
        monkeypatch.setenv("FAIL_UNITTEST" if fail == "static" else "FAIL_PRIME_NATIVE", "1")
        with pytest.raises(subprocess.CalledProcessError) as failure:
            runner.main()
        assert failure.value.returncode == 19
        assert not any("-e" in call["args"] for call in calls(workspace))
        if fail == "static":
            assert all(not call["credentials"] for call in calls(workspace))
        else:
            assert calls(workspace)[-1]["credentials"] == ["NOTTE_API_KEY"]
        return
    runner.main()
    observed = calls(workspace)
    suites = [call for call in observed if "unittest" in call["args"]]
    assert len(suites) == 3
    assert suites[0]["credentials"] == []
    assert suites[0]["live_flags"]["NOTTE_PRIME_LIVE"] == "0"
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in suites[1:])
    assert all(call["live_flags"]["NOTTE_PRIME_LIVE"] == "1" for call in suites[1:])
    assert all(call["cwd"] == str(project) for call in observed)
    commands = [call["args"] for call in observed]
    assert not any(command[0] in {"npm", "npx"} for command in commands)
    assert commands[0] == ["uv", "sync", "--locked", "--python", "3.11"]
    source = next(call for call in observed if "-e" in call["args"])
    assert source["credentials"] == []
    assert "--no-deps" not in source["args"]
    assert source["args"][-6:] == [
        "-e",
        str(workspace / "packages/notte-core"),
        "-e",
        str(workspace / "packages/notte-sdk"),
        "-e",
        str(project),
    ]
    assert observed.index(source) > observed.index(suites[1])
    assert len([command for command in commands if command[:3] == ["uv", "pip", "check"]]) == 2


def test_python_profile_rejects_unknown_project_before_setup(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner.REGISTRY.write_text('{"alpha":"python-project"}')
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["alpha"]')
    with pytest.raises(ValueError, match="Unknown Python"):
        runner.projects("1/1")
    assert calls(workspace) == []


def test_yutori_keeps_python312_requirements_and_both_sdk_modes_without_vendor_credentials(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = shipped_project(workspace, monkeypatch, "yutori", "python-project")
    for module in ("main.py", "test_protocol.py", "test_browser.py"):
        (project / module).write_text("# Source fixture\n")
    monkeypatch.setenv("NOTTE_YUTORI_LIVE", "1")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-unused-provider")
    runner.main()
    observed = calls(workspace)
    commands = [call["args"] for call in observed]
    assert commands[0][-3:] == ["--clear", "--python", "3.12"]
    assert commands[1][-2:] == ["-r", "requirements.txt"]
    assert not any(command[0] in {"npm", "npx"} or "sync" in command for command in commands)
    suites = [call for call in observed if "unittest" in call["args"]]
    assert len(suites) == 3
    assert all(call["args"][-2:] == ["test_browser.py", "test_protocol.py"] for call in suites)
    assert suites[0]["credentials"] == [] and suites[0]["live_flags"]["NOTTE_YUTORI_LIVE"] == "0"
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in suites[1:])
    assert all(call["live_flags"]["NOTTE_YUTORI_LIVE"] == "1" for call in suites[1:])
    assert all(not call["credentials"] for call in observed if call not in suites)
    source = next(command for command in commands if "-e" in command)
    assert source[-4:] == ["-e", str(workspace / "packages/notte-core"), "-e", str(workspace / "packages/notte-sdk")]
    assert len([command for command in commands if command[:3] == ["uv", "pip", "check"]]) == 2


@pytest.mark.parametrize("failure", [None, "import", "native"])
def test_openagi_preserves_import_only_static_and_native_sdk_modes_without_vendor_key(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    project = shipped_project(workspace, monkeypatch, "openagi", "python-project")
    (project / "test_live.py").write_text("# Native module fixture\n")
    for flag in ("NOTTE_PRIME_LIVE", "NOTTE_YUTORI_LIVE", "NOTTE_OPENAGI_LIVE"):
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-unused-provider")
    if failure:
        monkeypatch.setenv("FAIL_OPENAGI_IMPORT" if failure == "import" else "FAIL_UNITTEST", "1")
        with pytest.raises(subprocess.CalledProcessError) as error:
            runner.main()
        assert error.value.returncode == (31 if failure == "import" else 19)
        assert not any("-e" in call["args"] for call in calls(workspace))
        return
    runner.main()
    observed = calls(workspace)
    commands = [call["args"] for call in observed]
    suites = [call for call in observed if "unittest" in call["args"]]
    assert len(suites) == 2
    assert all(call["args"] == ["python", "-m", "unittest", "-v", "test_live.py"] for call in suites)
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in suites)
    assert all(not call["credentials"] for call in observed if call not in suites)
    assert all(
        not {"NOTTE_PRIME_LIVE", "NOTTE_YUTORI_LIVE", "NOTTE_OPENAGI_LIVE"} & call["live_flags"].keys()
        for call in suites
    )
    assert all(call["cwd"] == str(project) for call in observed)
    assert commands[:4] == [
        ["uv", "sync", "--locked", "--python", "3.11"],
        ["uv", "pip", "check", "--python", str(project / ".venv/bin/python")],
        ["python", "-c", "import demo; from oagi import AsyncDefaultAgent"],
        ["python", "-m", "compileall", "-q", "demo.py", "notte_computer.py", "test_live.py"],
    ]
    source = next(command for command in commands if "-e" in command)
    assert source[-6:] == [
        "-e",
        str(workspace / "packages/notte-core"),
        "-e",
        str(workspace / "packages/notte-sdk"),
        "oagi-core==0.15.3",
        "playwright==1.64.0",
    ]
    assert str(project) not in source and "--no-deps" not in source
    assert not any(command[0] in {"npm", "npx"} for command in commands)
    assert commands.index(source) > commands.index(suites[0]["args"])
    assert commands.count(["uv", "pip", "check", "--python", str(project / ".venv/bin/python")]) == 2


@pytest.mark.parametrize("failure", [None, "import", "python", "node"])
def test_pipedream_keeps_independent_native_languages_and_real_python_without_vendor_context(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    project = shipped_project(workspace, monkeypatch, "pipedream", "python-project")
    (project / "test_live.py").write_text("# Native module fixture\n")
    for flag in ("NOTTE_PRIME_LIVE", "NOTTE_YUTORI_LIVE", "NOTTE_PIPEDREAM_LIVE"):
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    for key in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(key, "fixture-unused-provider")
    if failure:
        monkeypatch.setenv(
            {"import": "FAIL_PIPEDREAM_IMPORT", "python": "FAIL_UNITTEST", "node": "FAIL_PIPEDREAM_NODE"}[failure], "1"
        )
        with pytest.raises(subprocess.CalledProcessError) as error:
            runner.main()
        assert error.value.returncode == {"import": 31, "python": 19, "node": 23}[failure]
        assert not any("-e" in call["args"] for call in calls(workspace))
        return
    runner.main()
    observed = calls(workspace)
    commands = [call["args"] for call in observed]
    python = project / ".venv/bin/python"
    suites = [call for call in observed if "unittest" in call["args"] or call["args"] == ["npm", "test"]]
    assert len(suites) == 4
    assert [call["args"] for call in suites] == [
        ["python", "-m", "unittest", "-v", "test_live.py"],
        ["npm", "test"],
    ] * 2
    assert all(call["example_python"] == str(python) for call in suites)
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in suites)
    assert all(not call["credentials"] for call in observed if call not in suites)
    assert all(
        not {"NOTTE_PRIME_LIVE", "NOTTE_YUTORI_LIVE", "NOTTE_PIPEDREAM_LIVE"} & call["live_flags"].keys()
        for call in suites
    )
    assert all(call["cwd"] == str(project) for call in observed)
    assert commands[:5] == [
        ["uv", "sync", "--locked", "--python", "3.11"],
        ["uv", "pip", "check", "--python", str(python)],
        ["python", "-c", "import demo"],
        ["npm", "ci"],
        ["npm", "run", "typecheck"],
    ]
    source = next(command for command in commands if "-e" in command)
    assert source[-6:] == [
        "-e",
        str(workspace / "packages/notte-core"),
        "-e",
        str(workspace / "packages/notte-sdk"),
        "mcp==2.3.0",
        "httpx2==2.13.1",
    ]
    assert str(project) not in source and "--no-deps" not in source
    assert commands.index(source) > commands.index(suites[1]["args"])
    assert ["npm", "install", "--no-save", str(workspace / "node-sdk")] in commands
    assert not any("compileall" in command or "test:live" in command for command in commands)
    assert commands.count(["uv", "pip", "check", "--python", str(python)]) == 2


@pytest.fixture
def terraform_project(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runner.REGISTRY.write_text('{"terraform-profiles":"terraform-go"}')
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["terraform-profiles"]')
    monkeypatch.setenv("NOTTE_TERRAFORM_LIVE", "1")
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(zipfile.ZipInfo("terraform"), b"fixture Terraform CLI")
    monkeypatch.setattr(runner, "TERRAFORM_SHA256", hashlib.sha256(data.getvalue()).hexdigest())
    project = workspace / "integrations/terraform-provider-notte"
    project.mkdir(parents=True)
    return project


@pytest.mark.parametrize("fail", [False, True])
def test_terraform_keeps_static_loopback_and_one_uncached_live_wire_owner(
    workspace: Path, terraform_project: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    for credential in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(credential, "fixture-unused-provider")
    if fail:
        monkeypatch.setenv("FAIL_TERRAFORM_LIVE", "1")
        with pytest.raises(subprocess.CalledProcessError) as error:
            runner.main()
        assert error.value.returncode == 31
    else:
        runner.main()
    observed = calls(workspace)
    assert all(call["cwd"] == str(terraform_project) for call in observed)
    assert observed[0]["args"] == ["go", "test", "-race", "./..."]
    assert observed[-1]["args"] == ["go", "test", "-count=1", "-run", "^TestLiveProfileWire$", "-v", "."]
    assert all(not call["credentials"] for call in observed[:-1])
    assert all(call["live_flags"]["NOTTE_TERRAFORM_LIVE"] == "0" for call in observed[:-1])
    assert observed[-1]["credentials"] == ["NOTTE_API_KEY"]
    assert observed[-1]["live_flags"]["NOTTE_TERRAFORM_LIVE"] == "1"
    assert not any(call["args"][0] in {"npm", "npx"} for call in observed)
    assert len([call for call in observed if "test_cli" in call["args"]]) == 1
    assert os.access(workspace / "runner-temp/notte-terraform/terraform", os.X_OK)


def test_terraform_bad_checksum_never_extracts_or_runs_cli_or_native(
    workspace: Path, terraform_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "TERRAFORM_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.main()
    assert calls(workspace)[-1]["args"][0] == "curl"
    assert not (workspace / "runner-temp/notte-terraform/terraform").exists()


@pytest.mark.parametrize("fail", [False, True])
def test_e2e_preserves_unit_native_cli_modes_and_disables_telemetry(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    project = shipped_project(workspace, monkeypatch, "e2e", "node-project")
    for credential in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(credential, "fixture-unused-provider")
    if fail:
        monkeypatch.setenv("FAIL_NATIVE", "1")
        with pytest.raises(subprocess.CalledProcessError) as error:
            runner.main()
        assert error.value.returncode == 23
        commands = [call["args"] for call in calls(workspace)]
        assert ["npm", "test"] not in commands
        assert not any(command[:2] == ["npm", "install"] for command in commands)
        return
    runner.main()
    observed = calls(workspace)
    commands = [call["args"] for call in observed]
    native = [call for call in observed if call["args"] in (["npm", "run", "test:live"], ["npm", "test"])]
    assert len(native) == 4
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in native)
    assert all(not call["credentials"] for call in observed if call not in native)
    assert all(call["e2e_telemetry"] == "1" for call in observed)
    assert all(call["cwd"] == str(project) for call in observed)
    assert commands == [
        ["npm", "ci"],
        ["npm", "run", "typecheck"],
        ["npm", "run", "test:unit"],
        ["npm", "run", "typecheck"],
        ["npm", "run", "test:unit"],
        ["npm", "run", "test:live"],
        ["npm", "test"],
        ["npm", "install", "--no-save", str(workspace / "node-sdk")],
        ["npm", "run", "typecheck"],
        ["npm", "run", "test:unit"],
        ["npm", "run", "test:live"],
        ["npm", "test"],
    ]


@pytest.mark.parametrize("name", ["eve", "fx"])
@pytest.mark.parametrize("fail", [False, True])
def test_native_npm_test_projects_preserve_modes_and_only_notte_credentials(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, fail: bool
) -> None:
    project = shipped_project(workspace, monkeypatch, name, "node-project")
    for credential in runner.CREDENTIALS - {"NOTTE_API_KEY"}:
        monkeypatch.setenv(credential, "fixture-unused-provider")
    if fail:
        monkeypatch.setenv("FAIL_NATIVE", "1")
        with pytest.raises(subprocess.CalledProcessError) as failure:
            runner.main()
        assert failure.value.returncode == 23
    else:
        runner.main()
    observed = calls(workspace)
    native = [call for call in observed if call["live_flags"].get(f"NOTTE_{name.upper()}_LIVE") == "1"]
    assert len(native) == (1 if fail else 2)
    assert all(call["args"] == ["npm", "test"] and call["cwd"] == str(project) for call in native)
    assert all(call["credentials"] == ["NOTTE_API_KEY"] for call in native)
    assert all(not call["credentials"] for call in observed if call not in native)
    commands = [call["args"] for call in observed]
    source = [command for command in commands if command[:2] == ["npm", "install"]]
    assert len(source) == (0 if fail else 1)
    assert not any(command[0] == "uv" or "test:live" in command for command in commands)
    assert commands.count(["npm", "run", "typecheck"]) == (2 if fail else 3)


def test_mongodb_live_owns_one_limited_fixture_and_original_source_suite(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shipped_project(workspace, monkeypatch, "mongodb", "NOTTE_DOCS_PYTHON")
    monkeypatch.setenv("MONGODB_URI", "mongodb://outside.invalid")
    monkeypatch.setattr(runner, "kernel_release", lambda: "7.0.0-1017-azure (Ubuntu 7.0.0-1017.17-azure 7.0.14)")
    runner.main()
    image = "mongo:7.0.45@sha256:c53852c00c23ca9f23fc39690350ffa9a80e3642fe8f96879726d8da0abe80a7"
    assert f"MongoDB fixture: {image} on Linux 7.0.0-1017-azure (Ubuntu 7.0.0-1017.17-azure 7.0.14)\n" in (
        capsys.readouterr().out
    )
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
    assert create[-1] == image
    assert all(call["args"][-1] == name for call in docker[1:])
    assert docker[-1]["args"] == ["docker", "rm", "--force", "--volumes", name]
    assert all(not call["credentials"] for call in docker)
    native = [call for call in observed if "vitest" in call["args"]]
    assert len(native) == 1
    assert native[0]["args"] == ["npx", "vitest", "run", "test/mongodb.integration.test.ts"]
    assert native[0]["mongodb_uri"] == "mongodb://127.0.0.1:27017"
    assert native[0]["docs_python"] == str(workspace / ".venv/bin/python")
    assert native[0]["live_flags"]["NOTTE_MONGODB_LIVE"] == "1"
    assert native[0]["credentials"] == ["MONGODB_URI", "NOTTE_API_KEY"]
    assert ["uv", "pip", "install", "pymongo==4.19.0"] in commands
    assert ["uv", "pip", "check"] in commands
    assert commands.index(docker[2]["args"]) < commands.index(native[0]["args"]) < commands.index(docker[3]["args"])


@pytest.mark.parametrize("signature", ["Ubuntu 7.0.0-1017.17-azure 7.0.14\n", None])
def test_kernel_release_adds_ubuntu_upstream_version_when_available(
    monkeypatch: pytest.MonkeyPatch, signature: str | None
) -> None:
    def read_text(path: Path) -> str:
        assert path == Path("/proc/version_signature")
        if signature is None:
            raise FileNotFoundError(path)
        return signature

    monkeypatch.setattr(runner.platform, "release", lambda: "7.0.0-1017-azure")
    monkeypatch.setattr(Path, "read_text", read_text)
    expected = "7.0.0-1017-azure (Ubuntu 7.0.0-1017.17-azure 7.0.14)" if signature else "7.0.0-1017-azure"
    assert runner.kernel_release() == expected


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


# Recorded from the reviewed 12-profile runner before future profile handlers.
PROFILE_FIXTURES = json.loads((Path(__file__).parent / "fixtures/integration_example_commands.json").read_text())
CURRENT_COMMANDS = PROFILE_FIXTURES["reviewed"]
ACTIVE_PROFILES = PROFILE_FIXTURES["active"]
FUTURE_PROFILES = PROFILE_FIXTURES["future"]
OWN_PROVIDER = {
    "anthropic-computer-use": "ANTHROPIC_API_KEY",
    "braintrust": "BRAINTRUST_API_KEY",
    "claude-agents": "ANTHROPIC_API_KEY",
    "deepagents": "ANTHROPIC_API_KEY",
    "gemini-computer-use": "GEMINI_API_KEY",
    "inngest": "ANTHROPIC_API_KEY",
    "laminar": "LMNR_PROJECT_API_KEY",
    "openai-agents": "OPENAI_API_KEY",
    "openai-computer-use": "OPENAI_API_KEY",
}


def existing_project(workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, convention: str) -> Path:
    project = shipped_project(workspace, monkeypatch, name, convention)
    (project / "typescript").mkdir(exist_ok=True)
    if convention == "root-unittest":
        (project / ("test_read_page.py" if name == "laminar" else "test_agent.py")).write_text("# Synthetic module\n")
    if name == "selenium":
        driver = project / ".drivers/chromedriver"
        driver.parent.mkdir(parents=True)
        driver.write_text("owned fixture\n")
        driver.chmod(0o755)
        monkeypatch.setenv("DRIVER_OUTPUT", str(driver))
    return project


@pytest.mark.parametrize("name", sorted(CURRENT_COMMANDS))
def test_reviewed_twelve_keep_command_order_in_synthetic_projects(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    existing_project(workspace, monkeypatch, name, CURRENT_COMMANDS[name]["convention"])
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(key, "fixture-provider")
    runner.main()
    normalized = [
        {
            "args": [arg.replace(str(workspace), "$ROOT") for arg in call["args"]],
            "cwd": call["cwd"].replace(str(workspace), "$ROOT"),
        }
        for call in calls(workspace)
    ]
    assert normalized == ([] if name in runner.AGENT_RECIPES else CURRENT_COMMANDS[name]["commands"])


@pytest.mark.parametrize("name", sorted(FUTURE_PROFILES))
@pytest.mark.parametrize("phase", ["checks", "live"])
def test_unregistered_future_profiles_cannot_install_or_execute(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, phase: str
) -> None:
    runner.REGISTRY.write_text(json.dumps(ACTIVE_PROFILES))
    monkeypatch.setenv("INTEGRATION_EXAMPLES", json.dumps([name]))
    monkeypatch.setattr("sys.argv", ["runner", phase])
    with pytest.raises(ValueError, match="Unknown integration"):
        runner.main()
    assert calls(workspace) == []


@pytest.mark.parametrize(
    "ref,event",
    [("refs/heads/main", "push"), ("refs/heads/main", "pull_request"), ("refs/pull/1/merge", "pull_request")],
)
def test_all_selected_profiles_receive_only_their_own_reviewed_main_provider(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, ref: str, event: str
) -> None:
    selected = {name: value["convention"] for name, value in CURRENT_COMMANDS.items()}
    selected.update(braintrust="typescript-driver", laminar="root-unittest")
    for name, convention in selected.items():
        existing_project(workspace, monkeypatch, name, convention)
    runner.REGISTRY.write_text(json.dumps(selected))
    monkeypatch.setenv("INTEGRATION_EXAMPLES", json.dumps(sorted(selected)))
    monkeypatch.setenv("GITHUB_REF", ref)
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("NOTTE_LAMINAR_EXPORT_LIVE", "1")
    monkeypatch.setenv("NOTTE_DEEPAGENTS_MODEL_LIVE", "1")
    for key in runner.CREDENTIALS:
        monkeypatch.setenv(key, "fixture-owned-provider")
    original = runner.live
    observed_names = []

    def observe(project: Path, python: Path, convention: str, env: dict[str, str], install_env: dict[str, str]) -> None:
        start = len(calls(workspace))
        original(project, python, convention, env, install_env)
        observed_names.append(project.name)
        native = [call for call in calls(workspace)[start:] if call["credentials"]]
        key = OWN_PROVIDER.get(project.name) if ref == "refs/heads/main" and event != "pull_request" else None
        expected = sorted(["NOTTE_API_KEY", *([key] if key else [])])
        if project.name == "openai-agents":
            expected = ["NOTTE_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"]
        elif project.name == "claude-agents":
            expected = ["ANTHROPIC_AUTH_TOKEN", "NOTTE_API_KEY", "OPENROUTER_API_KEY"]
        assert native and all(call["credentials"] == expected for call in native), project.name
        if project.name != "laminar" or not key:
            assert all(call["live_flags"]["NOTTE_LAMINAR_EXPORT_LIVE"] == "0" for call in native)
        if project.name != "deepagents" or not key:
            assert all(call["live_flags"]["NOTTE_DEEPAGENTS_MODEL_LIVE"] == "0" for call in native)

    monkeypatch.setattr(runner, "live", observe)
    runner.main()
    assert observed_names == sorted(set(selected) - runner.AGENT_RECIPES)
    assert all(
        not call["credentials"]
        for call in calls(workspace)
        if "ci" in call["args"] or "install" in call["args"] or "sync" in call["args"]
    )


@pytest.mark.parametrize(
    "convention", ["python-project", "terraform-go", "typescript-driver", "valtown-deno", "box-root"]
)
def test_fixed_future_conventions_reject_unknown_projects_before_tools(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, convention: str
) -> None:
    runner.REGISTRY.write_text(json.dumps({"unknown-project": convention}))
    monkeypatch.setenv("INTEGRATION_EXAMPLES", '["unknown-project"]')
    monkeypatch.setattr("sys.argv", ["runner", "live"])
    with pytest.raises(ValueError, match="Unknown"):
        runner.main()
    assert calls(workspace) == []


@pytest.mark.parametrize("name", ["openai-agents", "claude-agents"])
def test_native_agent_credentials_only_come_from_openrouter(name: str) -> None:
    key = "fixture-openrouter"
    env = runner.project_env(
        name,
        {
            "GITHUB_REF": "refs/pull/1/merge",
            "GITHUB_EVENT_NAME": "pull_request",
            "NOTTE_API_KEY": "fixture-api",  # pragma: allowlist secret
            "OPENROUTER_API_KEY": key,
            "OPENAI_API_KEY": "wrong-direct-key",  # pragma: allowlist secret
            "ANTHROPIC_API_KEY": "wrong-direct-key",  # pragma: allowlist secret
            "GEMINI_API_KEY": "wrong-direct-key",  # pragma: allowlist secret
        },
    )
    assert env["OPENROUTER_API_KEY"] == key
    assert "wrong-direct-key" not in env.values()
    if name == "openai-agents":
        assert env["OPENAI_API_KEY"] == key
        assert env["OPENAI_BASE_URL"] == "https://openrouter.ai/api/v1"
    else:
        assert env["ANTHROPIC_API_KEY"] == ""
        assert env["ANTHROPIC_AUTH_TOKEN"] == key
        assert env["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"


@pytest.mark.parametrize("name", sorted(runner.AGENT_RECIPES))
@pytest.mark.parametrize("credential", sorted(runner.CREDENTIALS))
def test_agent_preparation_rejects_credentials_in_the_parent(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, credential: str
) -> None:
    shipped_project(workspace, monkeypatch, name, "NOTTE_DOCS_PYTHON")
    for key in runner.CREDENTIALS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(credential, "fixture-private-value")
    monkeypatch.setattr("sys.argv", ["runner", "prepare-agent"])
    with pytest.raises(ValueError, match="must not receive credentials"):
        runner.main()
    assert calls(workspace) == []


@pytest.mark.parametrize("name", sorted(runner.AGENT_RECIPES))
def test_agent_preparation_rejects_credentials_passed_to_the_helper(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    for key in runner.CREDENTIALS:
        monkeypatch.delenv(key, raising=False)
    credentialed_env = {"OPENROUTER_API_KEY": "fixture-private-value"}  # pragma: allowlist secret
    with pytest.raises(ValueError, match="must not receive credentials"):
        runner.agent_recipe(name, "prepare-agent", credentialed_env)
    assert calls(workspace) == []


@pytest.mark.parametrize("name", sorted(runner.AGENT_RECIPES))
@pytest.mark.parametrize("credential", ["NOTTE_API_KEY", "OPENROUTER_API_KEY"])
def test_agent_tests_require_both_existing_keys_before_execution(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, credential: str
) -> None:
    shipped_project(workspace, monkeypatch, name, "NOTTE_DOCS_PYTHON")
    monkeypatch.delenv(credential, raising=False)
    monkeypatch.setattr("sys.argv", ["runner", "test-agent"])
    with pytest.raises(ValueError, match="require NOTTE_API_KEY and OPENROUTER_API_KEY"):
        runner.main()
    assert calls(workspace) == []


@pytest.mark.parametrize("name", sorted(runner.AGENT_RECIPES))
@pytest.mark.parametrize("field,value", [("AGENT_PENDING", "1"), ("AGENT_TOTAL", "0")])
def test_agent_model_report_cannot_accept_skipped_cases(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str, field: str, value: str
) -> None:
    shipped_project(workspace, monkeypatch, name, "NOTTE_DOCS_PYTHON")
    monkeypatch.setenv(field, value)
    with pytest.raises(RuntimeError, match="without skips"):
        agent_phases(monkeypatch)
    native = [call for call in calls(workspace) if call["credentials"]]
    assert len(native) == 1
    assert native[0]["args"][0] == "vitest"


@pytest.mark.parametrize("name", sorted(runner.AGENT_RECIPES))
def test_shared_shards_defer_agent_models_to_the_required_jobs(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    shipped_project(workspace, monkeypatch, name, "NOTTE_DOCS_PYTHON")
    runner.main()
    assert calls(workspace) == []
    with pytest.raises(ValueError, match="separate prepare-agent and test-agent"):
        runner.recipe_live(name, workspace / ".venv/bin/python", dict(os.environ), {})
    assert calls(workspace) == []
