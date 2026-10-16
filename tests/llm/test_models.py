import pytest
from notte_core.errors import MissingAPIKeyForModel
from notte_llm.config import DEFAULT_BASE_URL, DEFAULT_MODEL, LlmSettings
from notte_llm.service import LLMService


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "NOTTE_LLM_BASE_URL",
        "NOTTE_LLM_MODEL",
        "NOTTE_LLM_API_KEY",
        "OPENROUTER_API_KEY",
        "NOTTE_LLM_TEMPERATURE",
        "NOTTE_LLM_NB_RETRIES_STRUCTURED_OUTPUT",
        "NOTTE_LLM_CONTEXT_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    settings = LlmSettings.from_env()
    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.model == DEFAULT_MODEL
    assert settings.temperature == 0
    assert settings.nb_retries_structured_output == 2
    assert settings.context_tokens == 128000


def test_explicit_key_takes_precedence(monkeypatch):
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "chosen-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fallback-key")
    assert LlmSettings.from_env().require_api_key() == "chosen-key"
    assert "chosen-key" not in repr(LlmSettings.from_env())


def test_default_endpoint_uses_openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fallback-key")
    assert LlmSettings.from_env().require_api_key() == "fallback-key"


def test_custom_endpoint_requires_a_model(monkeypatch):
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", "http://localhost:11434/v1/")
    with pytest.raises(ValueError, match="NOTTE_LLM_MODEL"):
        LlmSettings.from_env()
    assert LlmSettings.from_env(model="local-model").model == "local-model"


def test_custom_endpoint_cannot_use_openrouter_key(monkeypatch):
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", "https://api.example.com/v1/")
    monkeypatch.setenv("NOTTE_LLM_MODEL", "vendor/model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fallback-key")
    settings = LlmSettings.from_env()
    assert settings.base_url == "https://api.example.com/v1"
    with pytest.raises(MissingAPIKeyForModel, match="NOTTE_LLM_API_KEY") as e:
        settings.require_api_key()
    assert "OPENROUTER_API_KEY" not in str(e.value)


def test_missing_default_key_names_both_variables():
    with pytest.raises(MissingAPIKeyForModel, match="NOTTE_LLM_API_KEY or OPENROUTER_API_KEY"):
        LlmSettings.from_env().require_api_key()


def test_settings_read_environment(monkeypatch):
    monkeypatch.setenv("NOTTE_LLM_MODEL", "vendor/custom-model")
    monkeypatch.setenv("NOTTE_LLM_TEMPERATURE", "0.5")
    monkeypatch.setenv("NOTTE_LLM_NB_RETRIES_STRUCTURED_OUTPUT", "5")
    monkeypatch.setenv("NOTTE_LLM_CONTEXT_TOKENS", "4096")
    settings = LlmSettings.from_env()
    assert settings.model == "vendor/custom-model"
    assert settings.temperature == 0.5
    assert settings.nb_retries_structured_output == 5
    assert settings.context_tokens == 4096


@pytest.mark.parametrize(
    "url", ["ftp://example.com", "example.com", "https://key@example.com/v1", "https://example.com?key=secret"]
)
def test_invalid_base_url(url, monkeypatch):
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", url)
    with pytest.raises(ValueError, match="NOTTE_LLM_BASE_URL"):
        LlmSettings.from_env()


def test_character_clipping_respects_context_budget(monkeypatch):
    monkeypatch.setenv("NOTTE_LLM_CONTEXT_TOKENS", "2002")
    service = LLMService()
    assert service.context_length() == 2002
    assert service.clip_tokens("abc🙂" * 5) == "abc🙂" * 2
    assert service.clip_tokens("abc", max_tokens=0) == ""
    assert service.clip_tokens("abc", max_tokens=10) == "abc"
    with pytest.raises(ValueError):
        service.clip_tokens("abc", max_tokens=-1)
