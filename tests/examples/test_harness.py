import json
import runpy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pytest_examples import CodeExample

from tests.examples import test_examples, test_readme


def test_legacy_discovery_leaves_registered_projects_to_the_shared_runner() -> None:
    registered: dict[str, str] = json.loads(test_examples.REGISTRY.read_text())
    legacy = test_examples.get_use_cases_dirs()

    assert {path.name for path in legacy} == {"scrape-nike-products", "session-solve-captcha"}
    assert not set(registered).intersection(path.name for path in legacy)
    assert [path.name for path in test_examples.get_python_files()] == ["quickstart.py"]


def test_new_unregistered_directory_is_not_silently_dropped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    examples = tmp_path / "examples"
    examples.mkdir()
    unregistered = examples / "new-example"
    unregistered.mkdir()
    registered = examples / "registered-example"
    registered.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({registered.name: "root-unittest"}))
    monkeypatch.setattr(test_examples, "REGISTRY", registry)
    monkeypatch.setattr(test_examples, "__file__", str(tmp_path / "tests/examples/test_examples.py"))

    assert test_examples.get_use_cases_dirs() == [unregistered]
    with pytest.raises(AssertionError, match="No example script found"):
        test_examples.test_use_case_script(unregistered)


def test_legacy_entrypoint_failure_preserves_exit_code_and_output(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text("import sys\nprint('original example failure')\nsys.exit(23)\n")

    with pytest.raises(AssertionError, match="exit code 23") as failure:
        test_examples.test_use_case_script(tmp_path)
    assert "original example failure" in str(failure.value)


@pytest.mark.parametrize(
    "directory,entrypoint,args",
    [
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
    with patch("notte_sdk.NotteClient") as client_type:
        namespace = runpy.run_path(str(script))
    context = client_type.return_value.Session.return_value
    session = context.__enter__.return_value

    def replay_after_close():
        context.__exit__.assert_called_once()
        return Mock(spec=["download"])

    session.replay.side_effect = replay_after_close
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
