import pytest
from notte_browser.llm.config import LlmSettings
from notte_browser.llm.models import LlmModel


def test_default_llm_model_uses_vertex_with_google_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    assert LlmModel.default() == "vertex_ai/gemini-3.5-flash"


def test_default_llm_model_uses_gemini_without_google_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert LlmModel.default() == "gemini/gemini-3.5-flash"


def test_llm_settings_default_to_the_default_model(monkeypatch: pytest.MonkeyPatch):
    for var in ("NOTTE_LLM_MODEL", "NOTTE_LLM_NB_RETRIES_STRUCTURED_OUTPUT", "NOTTE_LLM_TEMPERATURE"):
        monkeypatch.delenv(var, raising=False)
    settings = LlmSettings.from_env()
    assert settings.model == LlmModel.default().value
    assert settings.nb_retries_structured_output == 2
    assert settings.temperature == 0.0


def test_llm_settings_read_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOTTE_LLM_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("NOTTE_LLM_NB_RETRIES_STRUCTURED_OUTPUT", "5")
    monkeypatch.setenv("NOTTE_LLM_TEMPERATURE", "0.5")
    settings = LlmSettings.from_env()
    assert settings.model == "openai/gpt-4o"
    assert settings.nb_retries_structured_output == 5
    assert settings.temperature == 0.5
