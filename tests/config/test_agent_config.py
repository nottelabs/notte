from notte_core.common.config import LlmModel, NotteConfig, RaiseCondition
from pydantic import field_validator


class _TestFalcoConfig(NotteConfig):
    reasoning_model: str = LlmModel.cerebras
    perception_model: str | None = LlmModel.groq
    max_steps: int = 10
    use_vision: bool = False
    max_history_tokens: int | None = None
    max_error_length: int = 500
    raise_condition: RaiseCondition = RaiseCondition.NEVER

    @field_validator("max_steps")
    def check_max_steps(cls, value: int) -> int:
        if value > 20:
            raise ValueError("max_steps must be less than or equal to 20")
        return value

    @field_validator("raise_condition")
    def check_raise_condition(cls, value: RaiseCondition) -> RaiseCondition:
        return RaiseCondition.NEVER


def test_agent_config_initialization():
    config = _TestFalcoConfig.from_toml()
    assert config.reasoning_model == LlmModel.cerebras
    assert config.perception_model == LlmModel.groq
    assert config.use_vision is True
    assert config.max_history_tokens is None
    assert config.max_error_length == 500
    assert config.max_consecutive_failures == 3
    assert config.raise_condition == "never"
    # TODO: define what we want here, since max_step = 20 in the toml file,
    # it will override the default value inside the TestFalcoConfig class
    assert config.max_steps == 20
