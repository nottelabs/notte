from notte_core.common.config import LlmModel, LlmProvider


FIREWORKS_MODELS: list[str] = [
    LlmModel.fireworks_kimi,
    LlmModel.fireworks_glm,
    LlmModel.fireworks_minimax,
]


def test_fireworks_provider_registered():
    assert LlmProvider.fireworks_ai in list(LlmProvider)
    assert str(LlmProvider.fireworks_ai) == "fireworks_ai"


def test_fireworks_provider_apikey_name():
    assert LlmProvider.fireworks_ai.apikey_name == "FIREWORKS_API_KEY"


def test_fireworks_get_provider_resolves():
    provider = LlmModel.get_provider("fireworks_ai/accounts/fireworks/models/kimi-k2p5")
    assert provider == LlmProvider.fireworks_ai


def test_fireworks_models_resolve_to_fireworks_provider():
    for model in FIREWORKS_MODELS:
        assert LlmModel.get_provider(model) == LlmProvider.fireworks_ai


def test_fireworks_models_use_non_strict_response_format():
    for model in FIREWORKS_MODELS:
        assert LlmModel.use_strict_response_format(model) is False


def test_fireworks_kimi_temperature_override_matches_moonshot():
    # Same underlying model, both paths should pick up the 1.0 override.
    assert LlmModel.get_temperature(LlmModel.fireworks_kimi, default=0.0) == 1.0
    assert LlmModel.get_temperature(LlmModel.kimi2_5, default=0.0) == 1.0
