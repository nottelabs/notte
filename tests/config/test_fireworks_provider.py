import os
from unittest.mock import patch

from notte_core.common.config import LlmModel, LlmProvider


class TestFireworksProviderRegistration:
    def test_fireworks_ai_is_valid_provider(self) -> None:
        assert LlmProvider.fireworks_ai == "fireworks_ai"
        assert LlmProvider.fireworks_ai in list(LlmProvider)

    def test_apikey_name(self) -> None:
        assert LlmProvider.fireworks_ai.apikey_name == "FIREWORKS_API_KEY"

    def test_is_prefix_provider(self) -> None:
        assert LlmProvider.fireworks_ai.is_prefix_provider is True

    def test_other_providers_are_not_prefix_providers(self) -> None:
        non_prefix = [p for p in LlmProvider if p != LlmProvider.fireworks_ai]
        for provider in non_prefix:
            assert provider.is_prefix_provider is False, f"{provider} should not be a prefix provider"

    def test_context_length_uses_default(self) -> None:
        assert LlmProvider.fireworks_ai.context_length == 128_000


class TestFireworksModelResolution:
    def test_get_provider_from_fireworks_path(self) -> None:
        model = "fireworks_ai/accounts/fireworks/models/kimi-k2p5"
        assert LlmModel.get_provider(model) == LlmProvider.fireworks_ai

    def test_get_provider_from_various_fireworks_models(self) -> None:
        models = [
            "fireworks_ai/accounts/fireworks/models/glm-5p2",
            "fireworks_ai/accounts/fireworks/models/minimax-m3",
            "fireworks_ai/accounts/fireworks/models/some-future-model",
        ]
        for model in models:
            assert LlmModel.get_provider(model) == LlmProvider.fireworks_ai


class TestFireworksValidation:
    @patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"})
    def test_arbitrary_fireworks_model_is_valid(self) -> None:
        assert LlmModel.is_valid("fireworks_ai/accounts/fireworks/models/kimi-k2p5")
        assert LlmModel.is_valid("fireworks_ai/accounts/fireworks/models/glm-5p2")
        assert LlmModel.is_valid("fireworks_ai/accounts/fireworks/models/any-future-model")

    def test_fireworks_model_invalid_without_api_key(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "FIREWORKS_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            assert not LlmModel.is_valid("fireworks_ai/accounts/fireworks/models/kimi-k2p5")

    def test_unknown_provider_is_invalid(self) -> None:
        assert not LlmModel.is_valid("notavalidprovider/some-model")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_enum_model_still_valid_via_is_valid(self) -> None:
        assert LlmModel.is_valid("openai/gpt-4o")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_non_prefix_provider_rejects_arbitrary_models(self) -> None:
        assert not LlmModel.is_valid("openai/some-unknown-model")


class TestFireworksResponseFormat:
    def test_fireworks_does_not_use_strict_response_format(self) -> None:
        assert not LlmModel.use_strict_response_format("fireworks_ai/accounts/fireworks/models/kimi-k2p5")
        assert not LlmModel.use_strict_response_format("fireworks_ai/accounts/fireworks/models/any-model")


class TestFireworksHasApiKeyInEnv:
    @patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"})
    def test_has_apikey_when_set(self) -> None:
        assert LlmProvider.fireworks_ai.has_apikey_in_env()

    def test_no_apikey_when_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "FIREWORKS_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            assert not LlmProvider.fireworks_ai.has_apikey_in_env()
