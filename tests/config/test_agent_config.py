from argparse import Namespace

from notte_agent.common.config import AgentConfig
from notte_browser.scraping.pipe import ScrapingType
from notte_browser.session import NotteSessionConfig
from notte_browser.tagging.action.pipe import ActionSpaceType
from notte_core.llms.engine import LlmModel
from typing_extensions import override


class TestAgentConfig(AgentConfig):
    @classmethod
    @override
    def default_session(cls) -> NotteSessionConfig:
        return (
            NotteSessionConfig(
                perception_model="test_model",
                max_steps=1,
            )
            .not_headless()
            .disable_perception()
        )


def test_agent_config_initialization():
    config = TestAgentConfig()
    assert config.reasoning_model == LlmModel.default()
    assert config.session.perception_model == "test_model"
    assert config.session.max_steps == 1
    assert config.include_screenshot is False
    assert config.max_history_tokens is None
    assert config.max_error_length == 500
    assert config.raise_condition == "retry"
    assert config.max_consecutive_failures == 3
    assert config.force_session is None
    assert config.session.window.headless is False


def test_groq_method():
    config = TestAgentConfig()
    updated_config = config.groq()
    assert updated_config.reasoning_model == "groq/llama-3.3-70b-versatile"


def test_openai_method():
    config = TestAgentConfig()
    updated_config = config.openai()
    assert updated_config.reasoning_model == "openai/gpt-4o"


def test_cerebras_method():
    config = TestAgentConfig()
    updated_config = config.cerebras()
    assert updated_config.reasoning_model == "cerebras/llama-3.3-70b"


def test_use_vision_method():
    config = TestAgentConfig()
    updated_config = config.use_vision()
    assert updated_config.include_screenshot is True


def test_dev_mode_method():
    config = TestAgentConfig()
    updated_config = config.dev_mode()
    assert updated_config.raise_condition == "immediately"
    assert updated_config.max_error_length == 1000


def test_map_session_method():
    config = TestAgentConfig()
    updated_config = config.map_session(lambda session: session.steps(30))
    assert updated_config.session.max_steps == 30


def test_from_args():
    args = Namespace(
        **{
            # "env.headless": True,
            "session.perception-model": "test_model_other",
            "session.max_steps": 100,
            "reasoning_model": "reasoning_model",
        }
    )
    config = TestAgentConfig.from_args(args)
    assert config.reasoning_model == "reasoning_model"
    assert config.session.window.headless is False
    assert config.session.perception_model == "test_model_other"
    assert config.session.max_steps == 100
    assert config.session.action.type is ActionSpaceType.SIMPLE
    assert config.session.scraping_type is ScrapingType.MARKDOWNIFY
    assert config.session.auto_scrape is False
