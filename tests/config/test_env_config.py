from notte.env import NotteEnvConfig
from notte.pipe.action.pipe import ActionSpaceType
from notte.pipe.preprocessing.pipe import PreprocessingType
from notte.pipe.scraping.pipe import ScrapingType
from notte.sdk.types import DEFAULT_MAX_NB_STEPS


def test_notte_env_config_initialization():
    config = NotteEnvConfig()
    assert config.verbose is False
    assert config.max_steps == DEFAULT_MAX_NB_STEPS


def test_dev_mode():
    config = NotteEnvConfig()
    updated_config = config.dev_mode()
    assert updated_config.verbose is True


def test_user_mode():
    config = NotteEnvConfig()
    updated_config = config.user_mode()
    assert updated_config.verbose is True
    assert updated_config.window.verbose is True
    assert updated_config.action.verbose is True


def test_groq():
    config = NotteEnvConfig()
    updated_config = config.groq()
    assert updated_config.perception_model == "groq/llama-3.3-70b-versatile"


def test_openai():
    config = NotteEnvConfig()
    updated_config = config.openai()
    assert updated_config.perception_model == "openai/gpt-4o"


def test_cerebras():
    config = NotteEnvConfig()
    updated_config = config.cerebras()
    assert updated_config.perception_model == "cerebras/llama-3.3-70b"


def test_a11y():
    config = NotteEnvConfig()
    updated_config = config.a11y()
    assert config.preprocessing.type is PreprocessingType.DOM
    assert updated_config.preprocessing.type is PreprocessingType.A11Y


def test_dom():
    config = NotteEnvConfig()
    updated_config = config.dom()
    assert config.preprocessing.type is PreprocessingType.DOM
    assert updated_config.preprocessing.type is PreprocessingType.DOM


def test_steps():
    config = NotteEnvConfig()
    updated_config = config.steps(20)
    assert updated_config.max_steps == 20


def test_headless():
    config = NotteEnvConfig()
    updated_config = config.headless(True)
    assert updated_config.window.headless is True


def test_not_headless():
    config = NotteEnvConfig()
    updated_config = config.not_headless()
    assert updated_config.window.headless is False


def test_cdp():
    config = NotteEnvConfig()
    updated_config = config.cdp("ws://example.com")
    assert updated_config.window.cdp_url == "ws://example.com"


def test_llm_action_tagging():
    config = NotteEnvConfig().disable_perception()
    updated_config = config.llm_action_tagging()
    assert config.action.type is ActionSpaceType.SIMPLE
    assert updated_config.action.type is ActionSpaceType.LLM_TAGGING


def test_llm_data_extract():
    config = NotteEnvConfig().disable_perception()
    updated_config = config.llm_data_extract()
    assert config.scraping.type is ScrapingType.SIMPLE
    assert updated_config.scraping.type == ScrapingType.LLM_EXTRACT


def test_disable_web_security():
    config = NotteEnvConfig()
    updated_config = config.disable_web_security()
    assert config.window.pool.web_security is False
    assert updated_config.window.pool.web_security is False


def test_enable_web_security():
    config = NotteEnvConfig().disable_web_security()
    updated_config = config.enable_web_security()
    assert config.window.pool.web_security is False
    assert updated_config.window.pool.web_security is True
