import runpy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pytest_examples import CodeExample

from tests.examples import test_examples, test_readme


@pytest.mark.parametrize(
    "directory,entrypoint,args",
    [
        ("landing-examples", "landing_examples.py", []),
        ("session-solve-captcha", "main.py", []),
        ("scrape-nike-products", "agent.py", ["--max-categories", "1"]),
    ],
)
def test_use_case_entrypoints(directory: str, entrypoint: str, args: list[str]):
    example_dir = Path(__file__).resolve().parents[2] / "examples" / directory
    with patch.object(test_examples, "run_python_file", return_value=(0, [])) as run:
        test_examples.test_use_case_script(example_dir)
    run.assert_called_once_with(example_dir / entrypoint, args)


def test_missing_example_configuration_skips_before_execution(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EXTERNAL_CDP_URL", raising=False)
    example = CodeExample.create("raise RuntimeError('must not run')", prefix='python requires-env="external_cdp_url"')
    evaluator = Mock()

    with pytest.raises(pytest.skip.Exception, match="EXTERNAL_CDP_URL"):
        test_readme.run_example_safely(example, evaluator)
    evaluator.run.assert_not_called()


def test_configured_example_still_reports_execution_errors(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EXTERNAL_CDP_URL", "ws://localhost:9222")
    example = CodeExample.create("bad_code()", prefix='python requires-env="external_cdp_url"')
    evaluator = Mock()
    evaluator.run.side_effect = NameError("bad_code is not defined")

    with pytest.raises(AssertionError, match="NameError: bad_code is not defined"):
        test_readme.run_example_safely(example, evaluator)
    evaluator.run.assert_called_once_with(example)


def test_nike_category_limit(tmp_path: Path):
    script = Path(__file__).resolve().parents[2] / "examples" / "scrape-nike-products" / "agent.py"
    with patch("notte_sdk.NotteClient"):
        namespace = runpy.run_path(str(script))
    scrape = namespace["scrape_nike_products"]
    categories = namespace["ProductCategories"].example()
    products = Mock(return_value=namespace["ShoppingList"](items=[]))

    with patch.dict(
        scrape.__globals__,
        RESULT_DIR=tmp_path,
        scrape_categories=Mock(return_value=categories),
        scrape_products=products,
    ):
        scrape(max_categories=1)

    assert products.call_count == 1
    assert len(list(tmp_path.glob("*/category_*.json"))) == 1
