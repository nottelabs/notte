from types import SimpleNamespace

import notte_core.common.config as config_module
import pytest
from notte_core.common.config import NotteConfig, config
from notte_core.errors import ErrorConfig
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


def test_config_file_with_removed_scraping_type_still_loads(tmp_path, monkeypatch):
    config_file = tmp_path / "notte.toml"
    _ = config_file.write_text('headless = false\nscraping_type = "main_content"\n')
    monkeypatch.setenv("NOTTE_CONFIG_PATH", str(config_file))
    warnings: list[str] = []
    monkeypatch.setattr(config_module, "logger", SimpleNamespace(warning=warnings.append))
    local_config = NotteConfig.from_toml()
    assert local_config.headless is False
    assert not hasattr(local_config, "scraping_type")
    assert warnings == [f"Ignoring unknown keys in config file {config_file}: scraping_type"]


def test_unknown_keyword_argument_is_still_rejected():
    with pytest.raises(ValidationError):
        _ = NotteConfig.from_toml(max_steps=20)  # pyright: ignore[reportCallIssue]


def test_config_file_with_retired_global_fields_warns_and_skips(tmp_path, monkeypatch):
    config_file = tmp_path / "notte.toml"
    _ = config_file.write_text('verbose = true\nlevel = "DEBUG"\nmax_error_length = 100\nsolve_captchas = true\n')
    monkeypatch.setenv("NOTTE_CONFIG_PATH", str(config_file))
    warnings: list[str] = []
    monkeypatch.setattr(config_module, "logger", SimpleNamespace(warning=warnings.append))

    local_config = NotteConfig.from_toml()

    assert local_config.verbose is True
    for field in ("level", "max_error_length", "solve_captchas"):
        assert not hasattr(local_config, field)
    assert warnings == [f"Ignoring unknown keys in config file {config_file}: level, max_error_length, solve_captchas"]
