"""Lossless action dumps plus public fields excluded by Pydantic serialization."""

import difflib
import json
import os
from pathlib import Path

import pytest
from notte_core.browser.observation import Observation


def render_actions(observation: Observation) -> str:
    # Do not filter model_dump(): future added fields must also cause a golden diff.
    # description/category/param can be excluded from the dump by their Field definitions.
    return (
        json.dumps(
            [
                {
                    "model_dump": action.model_dump(),
                    "description": action.description,
                    "category": action.category,
                    "param": None if action.param is None else action.param.model_dump(),
                }
                for action in observation.space.interaction_actions
            ],
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


def check_snapshot(path: Path, actual: str) -> None:
    if os.getenv("NOTTE_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(actual)
        return
    assert path.exists(), f"Missing golden file {path}: run with NOTTE_UPDATE_GOLDEN=1"
    expected = path.read_text()
    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(expected.splitlines(), actual.splitlines(), "expected", "actual", lineterm="", n=2)
        )
        pytest.fail(f"{path} changed (run with NOTTE_UPDATE_GOLDEN=1 if intended):\n{diff}", pytrace=False)


def capture_observations(fixture: str, output: Path, *, saved_page: bool = False) -> tuple[str, str]:
    # Setting os.environ within pytest is too late to affect Python's hash seed.
    # Isolate just the capture; the ordinary offline gate needs no special environment.
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "tests.characterization.capture", fixture, str(output)]
        + (["--saved-page"] if saved_page else []),
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONHASHSEED": "0"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    captured = json.loads(output.read_text())
    return captured["description"], captured["actions"]
