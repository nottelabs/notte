"""Run registered native Python/TypeScript examples inside the paired CI jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "scripts/integration_examples.json"
CREDENTIALS = {
    "NOTTE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "BRAINTRUST_API_KEY",
    "LMNR_PROJECT_API_KEY",
    "OP_SERVICE_ACCOUNT_TOKEN",
    "BOX_ACCESS_TOKEN",
    "AGENTCARD_CLIENT_ID",
    "AGENTCARD_CLIENT_SECRET",
}
DRIVER_IMPORTS = {
    "braintrust": "from braintrust import init_logger; from notte_sdk import NotteClient",
    "onepassword": 'from onepassword import Secrets; from notte_sdk import NotteClient; Secrets.validate_secret_reference("op://Test/Login/username")',
}
RECIPES = {"agent-browser", "claude-agents", "openai-agents"}
NODE_PROJECTS = {"agentcard", "docker-sandboxes", "inngest", "replit", "temporal", "trigger"}
DOCKER_CLI_SHA256 = "609a2e4b881ba9a7fd21543077e53d3b863a6b99eebee1f208e51a097ab56a05"  # pragma: allowlist secret


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
        if registry[name] not in {
            "node-project",
            "gemini-root",
            "selenium-root",
            "box-root",
            "root-unittest",
            "typescript-driver",
        } and not re.fullmatch(r"NOTTE_[A-Z0-9_]+_PYTHON", registry[name]):
            raise ValueError("Invalid integration registry convention")
        selected.add(name)
    index, count = map(int, shard.split("/"))
    if not 1 <= index <= count:
        raise ValueError("Shard must be index/count with 1 <= index <= count")
    return [(name, registry[name]) for name in sorted(selected)[index - 1 :: count]]


def run(command: list[str], directory: Path, env: dict[str, str]) -> None:
    _ = subprocess.run(command, cwd=directory, env=env, check=True)


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


def check(project: Path, env: dict[str, str], convention: str = "") -> Path:
    python = project / ".venv/bin/python"
    if project.name in RECIPES:
        # Shared checks typecheck the TypeScript SDK and docs recipes; Python setup runs in live.
        return ROOT / ".venv/bin/python"
    if convention == "node-project":
        run(["npm", "ci"], project, env)
        if project.name == "replit":
            run(["npm", "test"], project, env)
            return python
        run(["npm", "run", "build" if project.name == "temporal" else "typecheck"], project, env)
        if project.name in {"trigger", "agentcard", "docker-sandboxes"}:
            run(["npm", "test"], project, env)
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
            "NOTTE_BOX_CAPTURE_LIVE": "0",
            "NOTTE_BOX_LIVE": "0",
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
    run(["npm", "ci"], project / "typescript", env)
    run(["npm", "run", "typecheck"], project / "typescript", env)
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
        "claude-agents": "ANTHROPIC_API_KEY",
        "inngest": "ANTHROPIC_API_KEY",
    }.get(name)
    main = env.get("GITHUB_REF") == "refs/heads/main" and env.get("GITHUB_EVENT_NAME") != "pull_request"
    allowed = {"NOTTE_API_KEY", provider} if main else {"NOTTE_API_KEY"}
    return {key: value for key, value in env.items() if key not in CREDENTIALS or key in allowed}


def recipe_live(name: str, python: Path, env: dict[str, str], install_env: dict[str, str]) -> None:
    run(["uv", "sync", "--locked", "--package", "notte-sdk", "--no-dev"], ROOT, install_env)
    if name == "openai-agents":
        run(["uv", "pip", "install", "openai-agents==0.24.0", "pytest", "pytest-timeout"], ROOT, install_env)
        run(["uv", "run", "--no-sync", "pytest", "tests/sdk/test_websocket_compatibility.py", "-q"], ROOT, install_env)
    elif name == "claude-agents":
        run(["uv", "pip", "install", "claude-agent-sdk==0.2.168"], ROOT, install_env)
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
    run(["npx", "vitest", "run", f"test/{name}.integration.test.ts"], ROOT / "node-sdk", env)


def live(project: Path, python: Path, python_env: str, env: dict[str, str], install_env: dict[str, str]) -> None:
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
        env = {**project_env(project.name, env), f"NOTTE_{project.name.upper()}_LIVE": "1"}
        if project.name == "inngest":
            env["NOTTE_INNGEST_MODEL_LIVE"] = "1" if env.get("ANTHROPIC_API_KEY") else "0"
        for sdk in ("published", "source") if project.name in {"trigger", "agentcard"} else ("published",):
            if sdk == "source":
                run(
                    ["npm", "install", "--no-save", "--package-lock=false", str(ROOT / "node-sdk")],
                    project,
                    install_env,
                )
            print(f"Native integration: {project.name}, {sdk} SDK", flush=True)
            if project.name in {"trigger", "agentcard"}:
                run(["npm", "run", "typecheck"], project, install_env)
                run(["npm", "test"], project, install_env)
            run(["npm", "run", "test:live"], project, env)
        return
    if project.name == "github-actions":
        env = project_env(project.name, env)
        for sdk in ("published", "source"):
            if sdk == "source":
                python = ROOT / ".venv/bin/python"
                run(["uv", "sync", "--locked", "--package", "notte-sdk", "--no-dev"], ROOT, install_env)
                run(["uv", "pip", "install", "--python", str(python), "playwright==1.64.0"], ROOT, install_env)
                run(
                    ["npm", "install", "--no-save", "--package-lock=false", str(ROOT / "node-sdk")],
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
        env = {**env, f"NOTTE_{project.name.replace('-', '_').upper()}_PYTHON": str(python)}
    else:
        env = {**env, python_env: str(python)}
    typescript = project if root_layout else project / "typescript"
    for sdk in ("published", "source"):
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
                ["npm", "install", "--no-save", "--package-lock=false", str(ROOT / "node-sdk")],
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
        project = ROOT / "examples" / name
        print(f"Checking native integration: {name}", flush=True)
        python = check(project, install_env, python_env)
        if args.phase == "live":
            live(project, python, python_env, dict(os.environ), install_env)


if __name__ == "__main__":
    main()
