import pytest
from dotenv import load_dotenv
from pytest_examples import CodeExample, EvalExample, find_examples

_ = load_dotenv()


@pytest.mark.parametrize("example", find_examples("README.md"), ids=str)
def test_docstrings(example: CodeExample, eval_example: EvalExample):
    _ = eval_example.run(example)


@pytest.mark.parametrize("example", find_examples("docs/sdk_tutorial.md"), ids=str)
def test_sdk_tutorial(example: CodeExample, eval_example: EvalExample):
    _ = eval_example.run(example)


@pytest.mark.parametrize("example", find_examples("docs/run_notte_with_external_browsers"), ids=str)
def test_external_session_tutorial(example: CodeExample, eval_example: EvalExample):
    _ = eval_example.run(example)
