"""Run registered native Python/TypeScript examples inside the paired CI jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

if TYPE_CHECKING:
    from scripts.openapi_order import JsonValue

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "scripts/integration_examples.json"
CREDENTIALS = {
    "AGENTCARD_CLIENT_ID",
    "AGENTCARD_CLIENT_SECRET",
    "AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY",
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
}
DRIVER_IMPORTS = {
    "braintrust": "from braintrust import init_logger; from notte_sdk import NotteClient",
    "onepassword": 'from onepassword import Secrets; from notte_sdk import NotteClient; Secrets.validate_secret_reference("op://Test/Login/username")',
    "stripe-link": "from link import AsyncClient; from notte_sdk import AsyncNotteClient",
    "tzafon": "from tzafon import AsyncLightcone; from notte_sdk import NotteClient",
    "watsonx": "import requests; from notte_sdk import NotteClient",
}
RECIPES = {"agent-browser", "claude-agents", "mongodb", "openai-agents"}
NODE_PROJECTS = {"agentcard", "docker-sandboxes", "e2e", "eve", "fx", "inngest", "replit", "temporal", "trigger"}
# MongoDB 8.0+ refuses to start on Linux 6.19+ unless it recognizes the kernel fix (SERVER-121912),
# and reads Ubuntu's 7.0.14-based kernels as 7.0.0. 7.0 uses the legacy TCMalloc, which does not use rseq.
MONGODB_IMAGE = "mongo:7.0.45@sha256:c53852c00c23ca9f23fc39690350ffa9a80e3642fe8f96879726d8da0abe80a7"
DOCKER_CLI_SHA256 = "609a2e4b881ba9a7fd21543077e53d3b863a6b99eebee1f208e51a097ab56a05"  # pragma: allowlist secret

TERRAFORM_SHA256 = "38034b38d03096399a7a1264a14561a8029b2b496fd1f169452656e53968f1b7"  # pragma: allowlist secret


def projects(shard: str) -> list[tuple[str, str]]:
    registry: dict[str, str] = json.loads(REGISTRY.read_text())
    selection: object = json.loads(os.environ["INTEGRATION_EXAMPLES"])
    if not isinstance(selection, list):
        raise ValueError("INTEGRATION_EXAMPLES must be a JSON list of registered project names")
    selected: set[str] = set()
    for name in cast(list[object], selection):
        if not isinstance(name, str) or name not in registry or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError("Unknown integration example")
        if registry[name] == "node-project" and name not in NODE_PROJECTS:
            raise ValueError("Unknown Node integration project")
        if registry[name] == "python-project" and name not in {
            "prime-intellect",
            "yutori",
            "openagi",
            "pipedream",
            "e2b",
            "daytona",
            "boat",
        }:
            raise ValueError("Unknown Python integration project")
        if registry[name] == "terraform-go" and name != "terraform-profiles":
            raise ValueError("Unknown Terraform integration project")
        if registry[name] == "typescript-driver" and name not in DRIVER_IMPORTS:
            raise ValueError("Unknown TypeScript-driven integration project")
        if registry[name] == "valtown-deno" and name != "valtown":
            raise ValueError("Unknown Deno integration project")
        if registry[name] == "box-root" and name != "box":
            raise ValueError("Unknown Box integration project")
        if registry[name] not in {
            "node-project",
            "gemini-root",
            "selenium-root",
            "box-root",
            "root-unittest",
            "typescript-driver",
            "valtown-deno",
            "python-project",
            "terraform-go",
        } and not re.fullmatch(r"NOTTE_[A-Z0-9_]+_PYTHON", registry[name]):
            raise ValueError("Invalid integration registry convention")
        selected.add(name)
    index, count = map(int, shard.split("/"))
    if not 1 <= index <= count:
        raise ValueError("Shard must be index/count with 1 <= index <= count")
    return [(name, registry[name]) for name in sorted(selected)[index - 1 :: count]]


def run(command: list[str], directory: Path, env: dict[str, str]) -> None:
    _ = subprocess.run(command, cwd=directory, env=env, check=True)


def sdk_modes(name: str) -> tuple[str, ...]:
    """SDK inputs exercise source; project and periodic runs also check published pins."""
    source_only: JsonValue = json.loads(os.environ.get("INTEGRATION_SOURCE_ONLY", "[]"))
    selected: list[str] = json.loads(os.environ["INTEGRATION_EXAMPLES"])
    if not isinstance(source_only, list) or any(
        not isinstance(item, str) or item not in selected for item in source_only
    ):
        raise ValueError("INTEGRATION_SOURCE_ONLY must list selected integration examples")
    return ("source",) if name in source_only else ("published", "source")


def root_tests(project: Path) -> list[str]:
    tests = sorted(path.name for path in project.glob("test_*.py") if path.is_file())
    if not tests:
        raise ValueError("root-unittest requires root test_*.py modules")
    return tests


def docker_cli_contract(project: Path, env: dict[str, str]) -> None:
    prefix = Path(env["RUNNER_TEMP"]) / "notte-docker-sandboxes-cli"
    prefix.mkdir(parents=True, exist_ok=True)
    archive = prefix / "sbx.tar.gz"
    run(
        [
            "curl",
            "-fsSL",
            "https://github.com/docker/sbx-releases/releases/download/v0.48.0/DockerSandboxes-linux-amd64.tar.gz",
            "-o",
            str(archive),
        ],
        project,
        env,
    )
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != DOCKER_CLI_SHA256:
            raise ValueError("Docker Sandboxes CLI archive checksum mismatch")
    run(["tar", "-xzf", str(archive), "-C", str(prefix)], project, env)
    run(["node", "check-cli.mjs", str(prefix / "docker-sbx/sbx")], project, env)


def valtown_deno(env: dict[str, str]) -> Path:
    return (Path(env["RUNNER_TEMP"]) / "notte-valtown-deno/node_modules/.bin/deno").resolve(strict=True)


def check(project: Path, env: dict[str, str], convention: str = "") -> Path:
    python = project / ".venv/bin/python"
    if convention == "terraform-go":
        run(["go", "test", "-race", "./..."], project, env)
        prefix = Path(env["RUNNER_TEMP"]) / "notte-terraform"
        prefix.mkdir(parents=True, exist_ok=True)
        archive = prefix / "terraform.zip"
        run(
            [
                "curl",
                "-fsSL",
                "https://releases.hashicorp.com/terraform/1.16.6/terraform_1.16.6_linux_amd64.zip",
                "-o",
                str(archive),
            ],
            project,
            env,
        )
        with archive.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != TERRAFORM_SHA256:
                raise ValueError("Terraform CLI archive checksum mismatch")
        with zipfile.ZipFile(archive) as source:
            _ = source.extract("terraform", prefix)
        cli = prefix / "terraform"
        cli.chmod(0o755)
        python = prefix / "python/bin/python"
        run(["uv", "venv", str(prefix / "python"), "--clear", "--python", "3.11"], project, env)
        run(["uv", "pip", "install", "--python", str(python), "typing_extensions==4.16.0"], project, env)
        run([str(python), "-m", "unittest", "test_cli", "-v"], project, {**env, "TERRAFORM_BIN": str(cli)})
        return python
    if convention == "python-project":
        if project.name == "yutori":
            run(["uv", "venv", str(project / ".venv"), "--clear", "--python", "3.12"], project, env)
            run(["uv", "pip", "install", "--python", str(python), "-r", "requirements.txt"], project, env)
            run([str(python), "-m", "compileall", "-q", *sorted(p.name for p in project.glob("*.py"))], project, env)
        else:
            run(["uv", "sync", "--locked", "--python", "3.11"], project, env)
        run(["uv", "pip", "check", "--python", str(python)], project, env)
        if project.name in {"openagi", "pipedream"}:
            imports = "import demo; from oagi import AsyncDefaultAgent" if project.name == "openagi" else "import demo"
            run([str(python), "-c", imports], project, env)
            if project.name == "openagi":
                run(
                    [str(python), "-m", "compileall", "-q", "demo.py", "notte_computer.py", "test_live.py"],
                    project,
                    env,
                )
            else:
                run(["npm", "ci"], project, env)
                run(["npm", "run", "typecheck"], project, env)
        else:
            run([str(python), "-m", "unittest", "-v", *root_tests(project)], project, env)
        return python
    if convention == "valtown-deno":
        prefix = Path(env["RUNNER_TEMP"]) / "notte-valtown-deno"
        run(["npm", "install", "--prefix", str(prefix), "--no-audit", "--no-fund", "deno@2.9.6"], project, env)
        cli = str(valtown_deno(env))
        run([cli, "fmt", "--check", "main.ts", "main_test.ts", "deno.json"], project, env)
        run([cli, "lint", "main.ts", "main_test.ts"], project, env)
        run([cli, "task", "check"], project, env)
        run([cli, "task", "test"], project, env)
        return python
    if project.name in RECIPES:
        # Shared checks typecheck the TypeScript SDK and docs recipes; Python setup runs in live.
        return ROOT / ".venv/bin/python"
    if convention == "node-project":
        if project.name == "e2e":
            env = {**env, "E2E_TELEMETRY_DISABLED": "1"}
        run(["npm", "ci"], project, env)
        if project.name == "replit":
            run(["npm", "test"], project, env)
            return python
        run(["npm", "run", "build" if project.name == "temporal" else "typecheck"], project, env)
        if project.name in {"trigger", "agentcard", "docker-sandboxes", "eve", "fx"}:
            run(["npm", "test"], project, env)
        elif project.name == "e2e":
            run(["npm", "run", "test:unit"], project, env)
        if project.name == "docker-sandboxes":
            run(["sh", "-n", "setup.sh"], project, env)
            docker_cli_contract(project, env)
        return python
    if project.name == "github-actions":
        run(["uv", "sync", "--locked"], project, env)
        run(["uv", "pip", "check", "--python", str(python)], project, env)
        run([str(python), "-m", "unittest", "test_publish", "test_cli_signals", "-v"], project, env)
        run(["npm", "ci"], project, env)
        run(["npm", "run", "typecheck"], project, env)
        return python
    if convention in {"gemini-root", "selenium-root", "box-root"}:
        version = "3.11" if convention == "gemini-root" else "3.12"
        run(["uv", "venv", str(project / ".venv"), "--clear", "--python", version], project, env)
        run(["uv", "pip", "install", "--python", str(python), "-r", "requirements.txt"], project, env)
        run(["uv", "pip", "check", "--python", str(python)], project, env)
        run(["npm", "ci"], project, env)
        run(["npm", "run", "typecheck"], project, env)
        offline = {
            **env,
            "NOTTE_GEMINI_LIVE": "0",
            "NOTTE_GEMINI_MODEL_LIVE": "0",
            "NOTTE_SELENIUM_LIVE": "0",
            "DISABLE_TELEMETRY": "true",
        }
        if convention == "selenium-root":
            run(
                [
                    str(python),
                    "-m",
                    "compileall",
                    "-q",
                    "bridge.py",
                    "main.py",
                    "install_driver.py",
                    "test_selenium.py",
                ],
                project,
                offline,
            )
            run([str(python), "-m", "unittest", "-v", "test_bridge"], project, offline)
        elif convention == "box-root":
            offline.update(NOTTE_BOX_CAPTURE_LIVE="0", NOTTE_BOX_LIVE="0")
            run([str(python), "-m", "unittest", "-v", "test_upload"], project, offline)
            run(
                [str(python), "-m", "compileall", "-q", "main.py", "cleanup_case.py", "test_box.py", "test_capture.py"],
                project,
                offline,
            )
        else:
            run([str(python), "-m", "unittest", "-v", "test_agent.py"], project, offline)
        run(["npm", "test"], project, offline)
        return python
    tests = root_tests(project) if convention == "root-unittest" else []
    run(["uv", "sync", "--locked"], project, env)
    run(["uv", "pip", "check", "--python", str(python)], project, env)
    sources = sorted(path.name for path in project.glob("*.py") if path.is_file()) if tests else ["python"]
    run([str(python), "-m", "compileall", "-q", *sources], project, env)
    if convention == "typescript-driver":
        run([str(python), "-c", DRIVER_IMPORTS[project.name]], project, env)
        if project.name in {"stripe-link", "watsonx", "tzafon"}:
            run([str(python), "-m", "unittest", "discover", "-s", "python"], project, env)
    run(["npm", "ci"], project / "typescript", env)
    run(["npm", "run", "typecheck"], project / "typescript", env)
    if convention == "typescript-driver" and project.name in {"stripe-link", "watsonx", "tzafon"}:
        run(["npm", "test"], project / "typescript", env)
    if tests:
        prefix = f"NOTTE_{project.name.replace('-', '_').upper()}"
        offline = {
            **env,
            f"{prefix}_LIVE": "0",
            f"{prefix}_MODEL_LIVE": "0",
            f"{prefix}_EXPORT_LIVE": "0",
            "LANGSMITH_TRACING": "false",
            "DISABLE_TELEMETRY": "true",
        }
        run([str(python), "-m", "unittest", "-v", *tests], project, offline)
        run(["npm", "run", "test:live"], project / "typescript", offline)
    return python


def selenium_driver(project: Path, python: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        [str(python), "install_driver.py"], cwd=project, env=env, check=True, text=True, stdout=subprocess.PIPE
    )
    output = result.stdout.strip()
    driver = Path(output)
    if (
        not output
        or len(output.splitlines()) != 1
        or not driver.is_absolute()
        or not driver.resolve().is_relative_to((project / ".drivers").resolve())
        or not driver.is_file()
        or not os.access(driver, os.X_OK)
    ):
        raise ValueError("Selenium setup did not return an owned executable driver path")
    return str(driver.resolve())


def project_env(name: str, env: dict[str, str]) -> dict[str, str]:
    provider = {
        "openai-agents": "OPENAI_API_KEY",
        "openai-computer-use": "OPENAI_API_KEY",
        "claude-agents": "ANTHROPIC_API_KEY",
        "anthropic-computer-use": "ANTHROPIC_API_KEY",
        "deepagents": "ANTHROPIC_API_KEY",
        "gemini-computer-use": "GEMINI_API_KEY",
        "inngest": "ANTHROPIC_API_KEY",
        "braintrust": "BRAINTRUST_API_KEY",
        "laminar": "LMNR_PROJECT_API_KEY",
    }.get(name)
    main = env.get("GITHUB_REF") == "refs/heads/main" and env.get("GITHUB_EVENT_NAME") != "pull_request"
    allowed = {"NOTTE_API_KEY", provider} if main else {"NOTTE_API_KEY"}
    selected = {key: value for key, value in env.items() if key not in CREDENTIALS or key in allowed}
    # Native integrations use standard asyncio; published SDKs still opt into a loop patch.
    selected["NOTTE_ENABLE_NEST_ASYNCIO"] = "false"
    return selected


def container_diagnostics(name: str, env: dict[str, str]) -> str:
    """Return a failed container's state, last health checks, and log tail for the error message."""
    commands = (
        ["docker", "inspect", "--format", "{{json .State}}", name],
        ["docker", "logs", "--tail", "50", name],
    )
    output: list[str] = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=env, check=False, text=True, capture_output=True)
        output.append(f"$ {' '.join(command)}\n{result.stdout}{result.stderr}")
    return "\n".join(output)


def kernel_release() -> str:
    """Return `uname -r`, plus the upstream version Ubuntu kernels report separately."""
    try:
        return f"{platform.release()} ({Path('/proc/version_signature').read_text().strip()})"
    except OSError:
        return platform.release()


@contextmanager
def mongodb_fixture(env: dict[str, str]) -> Iterator[str]:
    name = f"notte-mongodb-{uuid4().hex}"
    print(f"MongoDB fixture: {MONGODB_IMAGE} on Linux {kernel_release()}", flush=True)
    run(
        [
            "docker",
            "create",
            "--name",
            name,
            "--publish",
            "127.0.0.1:27017:27017",
            "--memory",
            "768m",
            "--cpus",
            "1",
            "--health-cmd",
            "mongosh --quiet --eval 'db.adminCommand({ ping: 1 }).ok'",
            "--health-interval",
            "5s",
            "--health-timeout",
            "5s",
            "--health-retries",
            "20",
            MONGODB_IMAGE,
        ],
        ROOT,
        env,
    )
    try:
        run(["docker", "start", name], ROOT, env)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            status = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", name],
                cwd=ROOT,
                env=env,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
            if status == "healthy":
                yield "mongodb://127.0.0.1:27017"
                return
            if status != "starting":
                raise RuntimeError(f"Owned MongoDB fixture is {status}\n{container_diagnostics(name, env)}")
            time.sleep(2)
        raise TimeoutError(f"Owned MongoDB fixture did not become healthy\n{container_diagnostics(name, env)}")
    finally:
        primary = sys.exception()
        try:
            run(["docker", "rm", "--force", "--volumes", name], ROOT, env)
        except (OSError, subprocess.SubprocessError) as cleanup:
            message = "Failed to remove owned MongoDB fixture"
            if primary is None:
                raise RuntimeError(message) from cleanup
            primary.add_note(message)


def recipe_live(name: str, python: Path, env: dict[str, str], install_env: dict[str, str]) -> None:
    run(["uv", "sync", "--locked", "--package", "notte-sdk", "--no-dev"], ROOT, install_env)
    if name == "openai-agents":
        run(["uv", "pip", "install", "openai-agents==0.24.0", "pytest", "pytest-timeout"], ROOT, install_env)
        run(["uv", "run", "--no-sync", "pytest", "tests/sdk/test_websocket_compatibility.py", "-q"], ROOT, install_env)
    elif name == "claude-agents":
        run(["uv", "pip", "install", "claude-agent-sdk==0.2.168"], ROOT, install_env)
        run(["uv", "pip", "check"], ROOT, install_env)
    elif name == "mongodb":
        run(["uv", "pip", "install", "pymongo==4.19.0"], ROOT, install_env)
        run(["uv", "pip", "check"], ROOT, install_env)
    if name != "agent-browser":
        run(["npm", "ci", "--prefix", "docs"], ROOT, install_env)
    env = {
        **env,
        "NOTTE_DOCS_PYTHON": str(python),
        "VITEST_INTEGRATION": "1",
        f"NOTTE_{name.replace('-', '_').upper()}_LIVE": "1",
    }
    print(f"Native integration: {name}, source SDK", flush=True)
    if name == "agent-browser":
        cli = Path(install_env["RUNNER_TEMP"]) / "notte-agent-browser"
        run(
            ["npm", "install", "--prefix", str(cli), "--no-audit", "--no-fund", "agent-browser@0.39.1"],
            ROOT,
            install_env,
        )
        env = {
            **env,
            "PATH": str(cli / "node_modules/.bin") + os.pathsep + env["PATH"],
            "NOTTE_AGENT_BROWSER_OWNERSHIP_JOURNAL": str(
                Path(install_env["RUNNER_TEMP"]) / "agent-browser-owned.jsonl"
            ),
        }
        run(
            [str(python), "-m", "unittest", "discover", "-s", "../tests/docs", "-p", "test_agent_browser_recipe.py"],
            ROOT / "node-sdk",
            env,
        )
        run(
            ["npx", "vitest", "run", "test/agent-browser.recipe.test.ts"],
            ROOT / "node-sdk",
            {**env, "VITEST_INTEGRATION": ""},
        )
    command = ["npx", "vitest", "run", f"test/{name}.integration.test.ts"]
    if name == "mongodb":
        with mongodb_fixture(install_env) as uri:
            run(command, ROOT / "node-sdk", {**env, "MONGODB_URI": uri})
    else:
        run(command, ROOT / "node-sdk", env)


def live(project: Path, python: Path, python_env: str, env: dict[str, str], install_env: dict[str, str]) -> None:
    env = project_env(project.name, env)
    if project.name != "laminar" or not env.get("LMNR_PROJECT_API_KEY"):
        env["NOTTE_LAMINAR_EXPORT_LIVE"] = "0"
    if project.name != "deepagents" or not env.get("ANTHROPIC_API_KEY"):
        env["NOTTE_DEEPAGENTS_MODEL_LIVE"] = "0"
    if python_env == "valtown-deno":
        env = {name: value for name, value in env.items() if name not in CREDENTIALS - {"NOTTE_API_KEY"}}
        run(
            [str(valtown_deno(install_env)), "task", "test:live"],
            project,
            {**env, "NOTTE_VALTOWN_LIVE": "1"},
        )
        return
    if python_env == "terraform-go":
        print("Native integration: Terraform profile API", flush=True)
        run(
            ["go", "test", "-count=1", "-run", "^TestLiveProfileWire$", "-v", "."],
            project,
            {**project_env("terraform-profiles", env), "NOTTE_TERRAFORM_LIVE": "1"},
        )
        return
    if python_env == "python-project":
        flags = {"prime-intellect": "NOTTE_PRIME_LIVE", "yutori": "NOTTE_YUTORI_LIVE"}
        env = {**project_env(project.name, env), "DISABLE_TELEMETRY": "true"}
        if flag := flags.get(project.name):
            env[flag] = "1"
        for sdk in sdk_modes(project.name):
            if sdk == "source":
                run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--python",
                        str(python),
                        "-e",
                        str(ROOT / "packages/notte-core"),
                        "-e",
                        str(ROOT / "packages/notte-sdk"),
                        *(["-e", str(project)] if project.name == "prime-intellect" else []),
                        *(["oagi-core==0.15.3", "playwright==1.64.0"] if project.name == "openagi" else []),
                        *(["mcp==2.3.0", "httpx2==2.13.1"] if project.name == "pipedream" else []),
                    ],
                    project,
                    install_env,
                )
                run(["uv", "pip", "check", "--python", str(python)], project, install_env)
                if project.name == "pipedream":
                    run(
                        ["npm", "install", "--no-save", str(ROOT / "node-sdk")],
                        project,
                        install_env,
                    )
                    run(["npm", "run", "typecheck"], project, install_env)
            print(f"Native integration: {project.name}, {sdk} SDK", flush=True)
            selected = {**env, "NOTTE_EXAMPLE_PYTHON": str(python)} if project.name == "pipedream" else env
            run([str(python), "-m", "unittest", "-v", *root_tests(project)], project, selected)
            if project.name == "pipedream":
                run(["npm", "test"], project, selected)
        return
    if project.name in RECIPES:
        recipe_live(project.name, python, project_env(project.name, env), install_env)
        return
    if python_env == "node-project":
        if project.name in {"replit", "docker-sandboxes"}:
            print(f"Native integration: {project.name}, hosted MCP", flush=True)
            selected_env = project_env(project.name, env)
            if project.name == "docker-sandboxes":
                selected_env["NOTTE_SANDBOXES_LIVE"] = "1"
            run(["npm", "run", "test:live"], project, selected_env)
            return
        if project.name == "e2e":
            env = {**project_env(project.name, env), "E2E_TELEMETRY_DISABLED": "1"}
            install_env = {**install_env, "E2E_TELEMETRY_DISABLED": "1"}
        else:
            env = {**project_env(project.name, env), f"NOTTE_{project.name.upper()}_LIVE": "1"}
        if project.name == "inngest":
            env["NOTTE_INNGEST_MODEL_LIVE"] = "1" if env.get("ANTHROPIC_API_KEY") else "0"
        for sdk in (
            sdk_modes(project.name) if project.name in {"trigger", "agentcard", "e2e", "eve", "fx"} else ("published",)
        ):
            if sdk == "source":
                run(
                    ["npm", "install", "--no-save", str(ROOT / "node-sdk")],
                    project,
                    install_env,
                )
            print(f"Native integration: {project.name}, {sdk} SDK", flush=True)
            if project.name in {"trigger", "agentcard", "e2e", "eve", "fx"}:
                run(["npm", "run", "typecheck"], project, install_env)
                run(["npm", "run", "test:unit"] if project.name == "e2e" else ["npm", "test"], project, install_env)
            run(["npm", "test"] if project.name in {"eve", "fx"} else ["npm", "run", "test:live"], project, env)
            if project.name == "e2e":
                run(["npm", "test"], project, env)
        return
    if project.name == "github-actions":
        env = project_env(project.name, env)
        for sdk in sdk_modes(project.name):
            if sdk == "source":
                python = ROOT / ".venv/bin/python"
                run(["uv", "sync", "--locked", "--package", "notte-sdk", "--no-dev"], ROOT, install_env)
                run(["uv", "pip", "install", "--python", str(python), "playwright==1.64.0"], ROOT, install_env)
                run(
                    ["npm", "install", "--no-save", str(ROOT / "node-sdk")],
                    project,
                    install_env,
                )
            print(f"Native integration: {project.name}, {sdk} SDK", flush=True)
            selected = {**env, python_env: str(python)}
            run([str(python), "-m", "unittest", "test_cli_signals", "test_live", "-v"], project, selected)
            run(["npm", "test"], project, selected)
        return
    root_layout = python_env in {"gemini-root", "selenium-root", "box-root"}
    if python_env == "gemini-root":
        env = {**env, "NOTTE_GEMINI_LIVE": "1", "NOTTE_GEMINI_MODEL_LIVE": "0", "DISABLE_TELEMETRY": "true"}
    elif python_env == "selenium-root":
        env = {name: value for name, value in env.items() if name not in CREDENTIALS - {"NOTTE_API_KEY"}}
        env = {**env, "NOTTE_SELENIUM_LIVE": "1", "DISABLE_TELEMETRY": "true"}
    elif python_env == "box-root":
        env = {name: value for name, value in env.items() if name not in CREDENTIALS - {"NOTTE_API_KEY"}}
        env = {**env, "NOTTE_BOX_CAPTURE_LIVE": "1", "NOTTE_BOX_LIVE": "0", "DISABLE_TELEMETRY": "true"}
    elif python_env == "root-unittest":
        prefix = f"NOTTE_{project.name.replace('-', '_').upper()}"
        env = {**env, f"{prefix}_LIVE": "1", "LANGSMITH_TRACING": "false", "DISABLE_TELEMETRY": "true"}
    elif python_env == "typescript-driver":
        if project.name in {"stripe-link", "watsonx", "tzafon"}:
            env = {name: value for name, value in env.items() if name not in CREDENTIALS - {"NOTTE_API_KEY"}}
            prefix = "LINK" if project.name == "stripe-link" else project.name.upper()
            env = {
                **env,
                f"NOTTE_{prefix}_PYTHON": str(python),
                f"NOTTE_{prefix}_REQUIRE_LIVE": "1",
                "DISABLE_TELEMETRY": "true",
            }
        else:
            env = {**env, f"NOTTE_{project.name.replace('-', '_').upper()}_PYTHON": str(python)}
    else:
        env = {**env, python_env: str(python)}
    typescript = project if root_layout else project / "typescript"
    for sdk in sdk_modes(project.name):
        if sdk == "source":
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "-e",
                    str(ROOT / "packages/notte-core"),
                    "-e",
                    str(ROOT / "packages/notte-sdk"),
                ],
                project,
                install_env,
            )
            run(["uv", "pip", "check", "--python", str(python)], project, install_env)
            run(
                ["npm", "install", "--no-save", str(ROOT / "node-sdk")],
                typescript,
                install_env,
            )
            run(["npm", "run", "typecheck"], typescript, install_env)
        print(f"Native integration: {project.name}, {sdk} SDK", flush=True)
        if python_env == "selenium-root":
            driver_env = {**env, "CHROMEDRIVER_PATH": selenium_driver(project, python, env)}
            run([str(python), "-m", "unittest", "-v", "test_selenium"], project, driver_env)
            run(["npm", "run", "test:live"], project, driver_env)
        elif python_env == "box-root":
            run([str(python), "-m", "unittest", "-v", "test_capture"], project, env)
            run(["npm", "run", "test:capture"], project, env)
        elif root_layout:
            run([str(python), "-m", "unittest", "-v", "test_agent.py"], project, env)
            run(["npm", "test"], project, env)
        elif python_env == "root-unittest":
            run([str(python), "-m", "unittest", "-v", *root_tests(project)], project, env)
            run(["npm", "run", "test:live"], typescript, env)
        elif python_env == "typescript-driver":
            run(["npm", "run", "test:live"], typescript, env)
        else:
            run([str(python), "-m", "unittest", "discover", "-s", "python", "-p", "test_live.py", "-v"], project, env)
            run(["npm", "run", "test:live"], typescript, env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("phase", choices=("checks", "live"))
    _ = parser.add_argument("--shard", default="1/1")
    args = parser.parse_args()
    selected = projects(args.shard)
    # Validate even recipes and hosted consumers before installs or credential use.
    _ = sdk_modes("")
    if args.phase == "live" and os.environ.get("GITHUB_ACTOR") == "dependabot[bot]":
        selected = [(name, convention) for name, convention in selected if name in {"inngest", "temporal"}]
    if args.phase == "live" and selected and not os.environ.get("NOTTE_API_KEY"):
        raise ValueError("NOTTE_API_KEY is required for native browser checks")
    install_env = {
        name: "0" if name.startswith("NOTTE_") and name.endswith("_LIVE") else value
        for name, value in os.environ.items()
        if name not in CREDENTIALS
    }
    install_env.update(LANGSMITH_TRACING="false", DISABLE_TELEMETRY="true")
    for name, python_env in selected:
        project = (
            ROOT / "integrations/terraform-provider-notte" if name == "terraform-profiles" else ROOT / "examples" / name
        )
        print(f"Checking native integration: {name}", flush=True)
        project_install_env = project_env(name, install_env)
        python = check(project, project_install_env, python_env)
        if args.phase == "live":
            live(project, python, python_env, dict(os.environ), project_install_env)


if __name__ == "__main__":
    main()
