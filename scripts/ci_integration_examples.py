"""Run registered native Python/TypeScript examples inside the paired CI jobs."""

from __future__ import annotations

import argparse
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
}
DRIVER_IMPORTS = {
    "braintrust": "from braintrust import init_logger; from notte_sdk import NotteClient",
    "onepassword": 'from onepassword import Secrets; from notte_sdk import NotteClient; Secrets.validate_secret_reference("op://Test/Login/username")',
}


def projects(shard: str) -> list[tuple[str, str]]:
    registry: dict[str, str] = json.loads(REGISTRY.read_text())
    selection: object = json.loads(os.environ["INTEGRATION_EXAMPLES"])
    if not isinstance(selection, list):
        raise ValueError("INTEGRATION_EXAMPLES must be a JSON list of registered project names")
    selected: set[str] = set()
    for name in cast(list[object], selection):
        if not isinstance(name, str) or name not in registry or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError("Unknown integration example")
        if registry[name] not in {
            "gemini-root",
            "selenium-root",
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


def check(project: Path, env: dict[str, str], convention: str = "") -> Path:
    python = project / ".venv/bin/python"
    if convention in {"gemini-root", "selenium-root"}:
        version = "3.12" if convention == "selenium-root" else "3.11"
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


def live(project: Path, python: Path, python_env: str, env: dict[str, str], install_env: dict[str, str]) -> None:
    root_layout = python_env in {"gemini-root", "selenium-root"}
    if python_env == "gemini-root":
        env = {**env, "NOTTE_GEMINI_LIVE": "1", "NOTTE_GEMINI_MODEL_LIVE": "0", "DISABLE_TELEMETRY": "true"}
    elif python_env == "selenium-root":
        env = {name: value for name, value in env.items() if name not in CREDENTIALS - {"NOTTE_API_KEY"}}
        env = {**env, "NOTTE_SELENIUM_LIVE": "1", "DISABLE_TELEMETRY": "true"}
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
