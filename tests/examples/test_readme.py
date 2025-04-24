import importlib
import subprocess
import sys

import pytest
from dotenv import load_dotenv
from pytest_examples import CodeExample, EvalExample, find_examples

_ = load_dotenv()


def _test_pip_install(package: str, import_statement: str):
    # import_statement = "from notte_sdk import NotteClient"

    _ = subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    importlib.import_module(import_statement)


def test_pip_install_notte_sdk():
    _test_pip_install("notte-sdk", "from notte_sdk import NotteClient")


@pytest.mark.parametrize("example", find_examples("README.md"), ids=str)
def test_docstrings(example: CodeExample, eval_example: EvalExample):
    _ = eval_example.run(example)


@pytest.mark.parametrize("example", find_examples("docs/sdk_tutorial.md"), ids=str)
def test_sdk_tutorial(example: CodeExample, eval_example: EvalExample):
    _ = eval_example.run(example)


@pytest.mark.parametrize("example", find_examples("docs/run_notte_with_external_browsers.md"), ids=str)
def test_external_session_tutorial(example: CodeExample, eval_example: EvalExample):
    _ = eval_example.run(example)


@pytest.mark.parametrize("example", find_examples("docs/scraping_tutorial.md"), ids=str)
def test_scraping_tutorial(example: CodeExample, eval_example: EvalExample):
    _ = eval_example.run(example)
