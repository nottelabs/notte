import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv
from pytest_examples import CodeExample, EvalExample, find_examples


def _test_pip_install(package: str, import_statement: str):
    _ = load_dotenv()
    # Create a temporary directory for the virtual environment
    temp_dir = Path(tempfile.mkdtemp())
    venv_path = temp_dir / "venv"

    try:
        # Create virtual environment
        _ = subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)])

        # Determine the path to the Python executable in the virtual environment
        if sys.platform == "win32":
            python_path = venv_path / "Scripts" / "python.exe"
        else:
            python_path = venv_path / "bin" / "python"

        # Install the package in the virtual environment
        _ = subprocess.check_call([str(python_path), "-m", "pip", "install", package])

        # Create a small script to import the module and run it
        test_script = temp_dir / "test_import.py"
        _ = test_script.write_text(import_statement)

        # Execute the script with the virtual environment's Python
        _ = subprocess.check_call([str(python_path), str(test_script)])
    finally:
        # Clean up the temporary directory and virtual environment
        shutil.rmtree(temp_dir)


def test_pip_install_notte_sdk():
    _test_pip_install("notte-sdk", "from notte_sdk import NotteClient")


@pytest.mark.skip(reason="Fails for some weird reason")
def test_pip_install_notte():
    _test_pip_install("notte", "from notte import Agent")


@pytest.mark.skip(reason="Fails for some weird reason")
def test_pip_install_notte_browser():
    _test_pip_install("notte-browser", "from notte_browser import NotteSession")


@pytest.mark.parametrize("example", find_examples("README.md"), ids=str)
def test_readme_python_code(example: CodeExample, eval_example: EvalExample):
    _ = load_dotenv()
    _ = eval_example.run(example)


@pytest.mark.parametrize("example", find_examples("docs/sdk_tutorial.md"), ids=str)
def test_sdk_tutorial(example: CodeExample, eval_example: EvalExample):
    _ = load_dotenv()
    _ = eval_example.run(example)


@pytest.mark.parametrize("example", find_examples("docs/run_notte_with_external_browsers.md"), ids=str)
def test_external_session_tutorial(example: CodeExample, eval_example: EvalExample):
    _ = load_dotenv()
    _ = eval_example.run(example)


@pytest.mark.parametrize("example", find_examples("docs/scraping_tutorial.md"), ids=str)
def test_scraping_tutorial(example: CodeExample, eval_example: EvalExample):
    _ = load_dotenv()
    _ = eval_example.run(example)


@pytest.mark.parametrize(
    "quickstart_example",
    [
        CodeExample(
            path="examples/quickstart.py",
            args=["Search Google for the price of a flight from New York to Paris", "5", "gemini/gemini-2.0-flash"],
        )
    ],
    ids=["quickstart.py"],
)
def test_quickstart(quickstart_example: CodeExample, eval_example: EvalExample):
    _ = load_dotenv()
    _ = eval_example.run(quickstart_example)
