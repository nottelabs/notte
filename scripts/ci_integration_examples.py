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
CREDENTIALS = {"NOTTE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"}


def projects(shard: str) -> list[tuple[str, str]]:
    registry: dict[str, str] = json.loads(REGISTRY.read_text())
    selection: object = json.loads(os.environ["INTEGRATION_EXAMPLES"])
    if not isinstance(selection, list):
        raise ValueError("INTEGRATION_EXAMPLES must be a JSON list of registered project names")
    selected: set[str] = set()
    for name in cast(list[object], selection):
        if not isinstance(name, str) or name not in registry or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError("Unknown integration example")
        if registry[name] != "gemini-root" and not re.fullmatch(r"NOTTE_[A-Z0-9_]+_PYTHON", registry[name]):
            raise ValueError("Invalid integration registry convention")
        selected.add(name)
    index, count = map(int, shard.split("/"))
    if not 1 <= index <= count:
        raise ValueError("Shard must be index/count with 1 <= index <= count")
    return [(name, registry[name]) for name in sorted(selected)[index - 1 :: count]]


def run(command: list[str], directory: Path, env: dict[str, str]) -> None:
    _ = subprocess.run(command, cwd=directory, env=env, check=True)


def check(project: Path, env: dict[str, str], convention: str = "") -> Path:
    python = project / ".venv/bin/python"
    if convention == "gemini-root":
        run(["uv", "venv", str(project / ".venv"), "--clear", "--python", "3.11"], project, env)
        run(["uv", "pip", "install", "--python", str(python), "-r", "requirements.txt"], project, env)
        run(["uv", "pip", "check", "--python", str(python)], project, env)
        run(["npm", "ci"], project, env)
        run(["npm", "run", "typecheck"], project, env)
        offline = {**env, "NOTTE_GEMINI_LIVE": "0", "NOTTE_GEMINI_MODEL_LIVE": "0", "DISABLE_TELEMETRY": "true"}
        run([str(python), "-m", "unittest", "-v", "test_agent.py"], project, offline)
        run(["npm", "test"], project, offline)
        return python
    run(["uv", "sync", "--locked"], project, env)
    run(["uv", "pip", "check", "--python", str(python)], project, env)
    run([str(python), "-m", "compileall", "-q", "python"], project, env)
    run(["npm", "ci"], project / "typescript", env)
    run(["npm", "run", "typecheck"], project / "typescript", env)
    return python


def live(project: Path, python: Path, python_env: str, env: dict[str, str], install_env: dict[str, str]) -> None:
    root_layout = python_env == "gemini-root"
    if root_layout:
        env = {**env, "NOTTE_GEMINI_LIVE": "1", "NOTTE_GEMINI_MODEL_LIVE": "0", "DISABLE_TELEMETRY": "true"}
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
        if root_layout:
            run([str(python), "-m", "unittest", "-v", "test_agent.py"], project, env)
            run(["npm", "test"], project, env)
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
    install_env = {name: value for name, value in os.environ.items() if name not in CREDENTIALS}
    for name, python_env in selected:
        project = ROOT / "examples" / name
        print(f"Checking native integration: {name}", flush=True)
        python = check(project, install_env, python_env)
        if args.phase == "live":
            live(project, python, python_env, dict(os.environ), install_env)


if __name__ == "__main__":
    main()
