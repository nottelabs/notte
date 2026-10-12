import pytest
from notte_core.common.config import NotteConfig, config
from notte_core.errors.base import ErrorConfig
from pydantic import ValidationError


def test_notte_session_config_initialization():
    config = NotteConfig.from_toml()
    assert config.verbose is False


def test_dev_mode():
    config = NotteConfig.from_toml(verbose=True)
    assert config.verbose is True


def test_headless():
    assert config.headless is True
    local_config = NotteConfig.from_toml(headless=True)
    assert local_config.headless is True


def test_not_headless():
    assert config.headless is True
    local_config = NotteConfig.from_toml(headless=False)
    assert local_config.headless is False


def test_enable_web_security():
    assert config.web_security is False
    local_config = NotteConfig.from_toml(web_security=True)
    assert local_config.web_security is True


def test_disable_web_security():
    assert config.web_security is False
    local_config = NotteConfig.from_toml(web_security=False)
    assert local_config.web_security is False


def test_error_mode_context_manager():
    with ErrorConfig.message_mode("developer"):
        assert ErrorConfig.get_message_mode().value == "developer"
    with ErrorConfig.message_mode("user"):
        assert ErrorConfig.get_message_mode().value == "user"
    with ErrorConfig.message_mode("agent"):
        assert ErrorConfig.get_message_mode().value == "agent"

    # double with statement test
    with ErrorConfig.message_mode("developer"):
        with ErrorConfig.message_mode("user"):
            assert ErrorConfig.get_message_mode().value == "user"
        assert ErrorConfig.get_message_mode().value == "developer"
        with ErrorConfig.message_mode("agent"):
            assert ErrorConfig.get_message_mode().value == "agent"
        assert ErrorConfig.get_message_mode().value == "developer"


def test_config_file_with_removed_keys_still_loads(tmp_path, monkeypatch):
    config_file = tmp_path / "notte.toml"
    _ = config_file.write_text(
        'verbose = true\nmax_steps = 20\nreasoning_model = "openai/gpt-4o"\nscreenshot_type = "last_action"\n'
    )
    monkeypatch.setenv("NOTTE_CONFIG_PATH", str(config_file))
    local_config = NotteConfig.from_toml()
    assert local_config.verbose is True
    assert not hasattr(local_config, "max_steps")
    assert not hasattr(local_config, "screenshot_type")


def test_unknown_keyword_argument_is_still_rejected():
    with pytest.raises(ValidationError):
        _ = NotteConfig.from_toml(max_steps=20)  # pyright: ignore[reportCallIssue]
