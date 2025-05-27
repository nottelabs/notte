from notte_core.common.config import LlmModel, NotteConfig, ScrapingType, config
from notte_sdk.types import DEFAULT_MAX_NB_STEPS


def test_notte_session_config_initialization():
    config = NotteConfig.from_toml()
    assert config.verbose is False
    assert config.max_steps == DEFAULT_MAX_NB_STEPS


def test_dev_mode():
    config = NotteConfig.from_toml(verbose=True)
    assert config.verbose is True


def test_groq():
    assert config.reasoning_model == LlmModel.default()
    local_config = NotteConfig.from_toml(reasoning_model=LlmModel.groq)
    assert local_config.reasoning_model == LlmModel.groq


def test_openai():
    assert config.perception_model is None
    local_config = NotteConfig.from_toml(perception_model=LlmModel.openai)
    assert local_config.perception_model == LlmModel.openai


def test_cerebras():
    assert config.perception_model is None
    local_config = NotteConfig.from_toml(perception_model=LlmModel.cerebras)
    assert local_config.perception_model == LlmModel.cerebras


def test_steps():
    assert config.max_steps == DEFAULT_MAX_NB_STEPS
    local_config = NotteConfig.from_toml(max_steps=100)
    assert local_config.max_steps == 100


def test_headless():
    assert config.headless is True
    local_config = NotteConfig.from_toml(headless=True)
    assert local_config.headless is True


def test_not_headless():
    assert config.headless is True
    local_config = NotteConfig.from_toml(headless=False)
    assert local_config.headless is False


def test_disable_perception():
    assert config.enable_perception is True
    local_config = NotteConfig.from_toml(enable_perception=False)
    assert local_config.enable_perception is False


def test_llm_data_extract():
    assert config.scraping_type is ScrapingType.MARKDOWNIFY
    local_config = NotteConfig.from_toml(scraping_type=ScrapingType.LLM_EXTRACT)
    assert local_config.scraping_type == ScrapingType.LLM_EXTRACT


def test_enable_web_security():
    assert config.web_security is False
    local_config = NotteConfig.from_toml(web_security=True)
    assert local_config.web_security is True


def test_disable_web_security():
    assert config.web_security is False
    local_config = NotteConfig.from_toml(web_security=False)
    assert local_config.web_security is False
