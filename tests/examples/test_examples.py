import subprocess
from pathlib import Path

import pytest


def find_python_files(directory: Path) -> list[Path]:
    """
    Find all Python files in the given directory, excluding __init__.py and test files.

    Args:
        directory: The directory to search in

    Returns:
        A list of Path objects for Python files
    """
    return [file for file in directory.glob("*.py") if file.name != "__init__.py" and not file.name.startswith("test_")]


def run_python_file(file_path: Path) -> str | None:
    """
    Run a Python file and return its output.

    Args:
        file_path: Path to the Python file

    Returns:
        The output of the Python file or None if there was an error
    """
    try:
        result = subprocess.run(["python", str(file_path)], capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running {file_path}: {e}")
        print(f"Error output: {e.stderr}")
        return None


def get_python_files() -> list[Path]:
    """
    Get all Python files in the examples directory.

    Returns:
        A list of Path objects for Python files
    """
    examples_dir = Path(__file__).parent.parent.parent / "examples"
    return find_python_files(examples_dir)


@pytest.mark.parametrize("python_file", get_python_files(), ids=lambda p: p.name)
def test_example_script(python_file: Path) -> None:
    """
    Test that a Python file runs without errors.

    Args:
        python_file: Path to the Python file to test
    """
    print(f"Running {python_file.name}...")
    output = run_python_file(python_file)

    assert output is not None, f"Failed to run {python_file.name}"
    print(f"Successfully ran {python_file.name}")
    print(f"Output: {output[:100]}...")  # Print first 100 chars of output


def test_github_automation():
    file_path = Path(__file__).parent.parent.parent / "examples" / "github_automation" / "agent.py"
    output = run_python_file(file_path)
    assert output is not None, f"Failed to run {file_path.name}"
    print(f"Successfully ran {file_path.name}")
    print(f"Output: {output[:100]}...")  # Print first 100 chars of output
