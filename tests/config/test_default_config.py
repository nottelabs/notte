import pytest
from notte_core.config import NotteConfig, config
from pydantic import ValidationError


def test_default_config():
    # these parameters are importants
    # Changing the default value needs to be motivated
    assert config.verbose is False
    assert config.logging_mode == "agent"
    assert config.raise_condition == "retry"
    assert config.timeout_goto_ms == 10000
    assert config.timeout_default_ms == 8000
    assert config.timeout_action_ms == 15000
    assert config.wait_retry_snapshot_ms == 1000
    assert config.wait_short_ms == 500
    assert config.empty_page_max_retry == 5
    assert config.viewport_expansion == 0
    assert config.evaluate_js_max_result_bytes == 16 * 1024 * 1024
    assert config.evaluate_js_max_result_values == 50_000


def test_default_is_headless():
    assert config.headless, "headless should be true by default for tests"


@pytest.mark.parametrize("limit", [0, -1])
def test_evaluate_js_limit_must_be_positive(limit: int):
    with pytest.raises(ValidationError, match="evaluate_js_max_result_bytes"):
        _ = NotteConfig.from_toml(evaluate_js_max_result_bytes=limit)


@pytest.mark.parametrize("limit", [0, -1])
def test_evaluate_js_value_limit_must_be_positive(limit: int):
    with pytest.raises(ValidationError, match="evaluate_js_max_result_values"):
        _ = NotteConfig.from_toml(evaluate_js_max_result_values=limit)
