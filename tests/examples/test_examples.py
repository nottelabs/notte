import logging
import os
import signal
import subprocess
import tempfile
from pathlib import Path

import pytest
from notte_core.common.config import LlmModel


def find_python_files(directory: Path) -> list[Path]:
    """
    Find all Python files in the given directory, excluding __init__.py and test files.

    Args:
        directory: The directory to search in

    Returns:
        A list of Path objects for Python files
    """
    return [file for file in directory.glob("*.py") if file.name != "__init__.py" and not file.name.startswith("test_")]


def run_python_file(file_path: Path, args: list[str], timeout_seconds: float = 280) -> tuple[int, list[str]]:
    """
    Run a Python file and return its output (both stdout and stderr).

    Args:
        file_path: Path to the Python file
        args: Command line arguments to pass to the Python file

    Returns:
        The error code
    """
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
        process = subprocess.Popen(
            ["python", str(file_path)] + args,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            # Examples should exercise open_viewer=True, but CI must not launch
            # a local browser whose lifecycle can keep the example alive.
            env={**os.environ, "BROWSER": "/bin/true"},
        )

        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            exit_code = -1
            logging.error("Timed out running %s after %s seconds", file_path, timeout_seconds)
        finally:
            # Viewer/browser processes may outlive the example. Stop the whole
            # process group so they cannot leak into later parametrized tests.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        output.seek(0)
        logged: list[str] = []
        for line in output:
            line = line.strip()
            if line:
                logged.append(line)
                logging.info(line)

        return exit_code, logged


def test_run_python_file_does_not_wait_for_descendant_stdout(tmp_path: Path) -> None:
    script = tmp_path / "spawns_descendant.py"
    script.write_text(
        "import os, subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "print('parent finished')\n"
        "print(os.environ['BROWSER'])\n"
    )

    exit_code, logs = run_python_file(script, [], timeout_seconds=5)

    assert exit_code == 0
    assert logs == ["parent finished", "/bin/true"]


def get_python_files() -> list[Path]:
    """
    Get all Python files in the examples directory.

    Returns:
        A list of Path objects for Python files
    """
    examples_dir = Path(__file__).parent.parent.parent / "examples"
    return find_python_files(examples_dir)


def get_use_cases_dirs(
    ignore_list: tuple[str, ...] = ("__pycache__",),
) -> list[Path]:
    """
    Get all use cases directories in the examples directory.

    Returns:
        A list of Path objects for example files
    """
    examples_dir = Path(__file__).parent.parent.parent / "examples"
    return [dir for dir in examples_dir.glob("*") if dir.is_dir() and dir.name not in ignore_list]


@pytest.mark.parametrize("python_file", get_python_files(), ids=lambda p: p.name)
def test_root_level_scripts(python_file: Path) -> None:
    """
    Test that a Python file runs without errors.

    Args:
        python_file: Path to the Python file to test
    """
    OVERRIDE_ARGS: dict[str, list[str]] = {
        "cli_agent.py": ["--task", "go to duckduckgo"],
        "quickstart.py": ["go to duckduckgo", "3", str(LlmModel.default())],
    }
    print(f"Running {python_file.name}...")
    exit_code, logs = run_python_file(python_file, OVERRIDE_ARGS.get(python_file.name, []))

    assert exit_code == 0, f"Failed to run {python_file.name} {logs[-1] if len(logs) > 0 else ''}"


@pytest.mark.parametrize("use_case_dir", get_use_cases_dirs(), ids=lambda p: p.name)
def test_use_case_script(use_case_dir: Path) -> None:
    """
    Test that a Python file runs without errors.

    Args:
        use_case_dir: Path to the use case directory to test
    """
    OVERRIDE_ARGS: dict[str, list[str]] = {"human-in-the-loop": ["--task", "go to duckduckgo"]}

    agent_file = use_case_dir / "agent.py"
    assert agent_file.exists(), f"No agent.py file found in {use_case_dir}"
    exit_code, logged = run_python_file(agent_file, OVERRIDE_ARGS.get(use_case_dir.name, []))

    if use_case_dir.name == "github-auto-issues-trending-repos":
        assert exit_code != 0
        assert logged[-1] == "KeyError: 'AUTO_ISSUES_GITHUB_EMAIL'"
    else:
        assert exit_code == 0, f"Failed to run {use_case_dir.name}"
