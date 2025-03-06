import pytest

from notte.agents.falco.agent import (
    FalcoAgentConfig as AgentConfig,
)
from notte.common.agent.config import DefaultAgentArgs, RaiseCondition


@pytest.fixture
def cli_args():
    return [
        f"--{DefaultAgentArgs.ENV_HEADLESS.with_prefix()}",
        f"--{DefaultAgentArgs.ENV_DISABLE_WEB_SECURITY.with_prefix()}",
        f"--{DefaultAgentArgs.ENV_PERCEPTION_MODEL.with_prefix()}",
        "model_x",
        f"--{DefaultAgentArgs.ENV_MAX_STEPS.with_prefix()}",
        "99",
    ]


def test_cli_config():
    parser = AgentConfig.create_parser()
    _ = parser.add_argument("--task", type=str, required=True, help="The task to run the agent on.")
    args = parser.parse_args(["--task", "open gflight and book cheapest flight from nyc"])
    config = AgentConfig.from_args(args).map_env(lambda env: env.enable_auto_scrape())
    assert config.env.auto_scrape is True
    assert config.env.window.pool.web_security is True
    assert config.env.window.headless is False


def test_agent_config_with_cli_args(cli_args: list[str]) -> None:
    parser = AgentConfig.create_parser()
    parsed_args = parser.parse_args(cli_args)
    config = AgentConfig.from_args(parsed_args)

    # Assertions to check if the configuration is as expected
    assert config.env.window.headless is True
    assert config.env.window.pool.web_security is False
    assert config.env.perception_model == "model_x"
    assert config.max_history_tokens == 16000  # Default value
    assert config.max_consecutive_failures == 3  # Default value
    assert config.raise_condition == RaiseCondition.RETRY  # Default value
    assert config.env.max_steps == 99  # Default value
