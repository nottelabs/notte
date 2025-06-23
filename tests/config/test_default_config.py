from notte_core.common.config import config


def test_default_config():
    # these parameters are importants
    # Changing the default value needs to be motivated
    assert config.verbose is False
    assert config.logging_mode == "agent"
    assert config.use_vision is True
    assert config.use_llamux is False
    assert config.raise_condition == "retry"
    assert config.max_error_length == 500
    assert config.max_consecutive_failures == 3
    assert config.timeout_goto_ms == 10000
    assert config.timeout_default_ms == 8000
    assert config.timeout_action_ms == 5000
    assert config.wait_retry_snapshot_ms == 1000
    assert config.wait_short_ms == 500
    assert config.empty_page_max_retry == 5
    assert config.viewport_expansion == 0


def test_default_is_headless():
    assert config.headless, "headless should be true by default for tests"
