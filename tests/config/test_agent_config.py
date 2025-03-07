from argparse import Namespace

from typing_extensions import override

from notte.common.agent.config import AgentConfig
from notte.env import NotteEnvConfig
from notte.llms.engine import LlmModel
from notte.pipe.action.pipe import ActionSpaceType
from notte.pipe.scraping.pipe import ScrapingType


class TestAgentConfig(AgentConfig):
    @classmethod
    @override
    def default_env(cls) -> NotteEnvConfig:
        return (
            NotteEnvConfig(
                perception_model="test_model",
                max_steps=1,
            )
            .not_headless()
            .disable_perception()
        )


def test_agent_config_initialization():
    config = TestAgentConfig()
    assert config.reasoning_model == LlmModel.default()
    assert config.env.perception_model == "test_model"
    assert config.env.max_steps == 1
    assert config.include_screenshot is False
    assert config.max_history_tokens == 16000
    assert config.max_error_length == 500
    assert config.raise_condition == "retry"
    assert config.max_consecutive_failures == 3
    assert config.force_env is None
    assert config.env.window.headless is False


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


def test_map_env_method():
    config = TestAgentConfig()
    updated_config = config.map_env(lambda env: env.steps(30))
    assert updated_config.env.max_steps == 30


def test_from_args():
    args = Namespace(
        **{
            # "env.headless": True,
            "env.perception-model": "test_model_other",
            "env.max_steps": 100,
            "reasoning_model": "reasoning_model",
        }
    )
    config = TestAgentConfig.from_args(args)
    assert config.reasoning_model == "reasoning_model"
    assert config.env.window.headless is False
    assert config.env.perception_model == "test_model_other"
    assert config.env.max_steps == 100
    assert config.env.action.type is ActionSpaceType.SIMPLE
    assert config.env.scraping.type is ScrapingType.SIMPLE
    assert config.env.auto_scrape is False
