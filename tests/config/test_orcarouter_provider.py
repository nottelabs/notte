import pytest
from notte_core.common.config import LlmModel, LlmProvider

from tests.llms.test_orcarouter_models import ORCAROUTER_MODELS

# Mapping from OrcaRouter provider names that differ from LlmProvider enum values.
# e.g. OrcaRouter uses "google" but LlmProvider uses "gemini".
ORCAROUTER_PROVIDER_ALIASES: dict[str, LlmProvider] = {
    "google": LlmProvider.gemini,
    "kimi": LlmProvider.moonshot,
    "grok": LlmProvider.xai,
    "z-ai": LlmProvider.zai,
}


def _resolve_orcarouter_provider(model: str) -> LlmProvider:
    """Resolve the OrcaRouter provider prefix to a LlmProvider."""
    prefix = model.split("/")[0]
    if prefix in ORCAROUTER_PROVIDER_ALIASES:
        return ORCAROUTER_PROVIDER_ALIASES[prefix]
    # Try direct match against LlmProvider values
    if prefix in list(LlmProvider):
        return LlmProvider(prefix)
    raise ValueError(
        f"OrcaRouter provider '{prefix}' (from model '{model}') "
        f"has no matching LlmProvider and no alias in ORCAROUTER_PROVIDER_ALIASES."
    )


class TestOrcarouterModelsHaveProvider:
    """Ensure every provider in ORCAROUTER_MODELS maps to a known LlmProvider."""

    @pytest.mark.parametrize("model", ORCAROUTER_MODELS)
    def test_orcarouter_model_has_known_provider(self, model: str) -> None:
        provider = _resolve_orcarouter_provider(model)
        assert isinstance(provider, LlmProvider)


class TestGetOrcarouterModel:
    """Tests for LlmModel.get_orcarouter_model() method."""

    def test_already_orcarouter_model_unchanged(self) -> None:
        model = "orcarouter/auto"
        assert LlmModel.get_orcarouter_model(model) == model

    def test_openrouter_model_is_stripped(self) -> None:
        result = LlmModel.get_orcarouter_model("openrouter/google/gemma-3-27b-it")
        assert result == "google/gemma-4-31b-it"

    def test_gpt_oss_120b_conversion(self) -> None:
        result = LlmModel.get_orcarouter_model("cerebras/gpt-oss-120b")
        assert result == "openai/gpt-5-mini"

    def test_gemini_conversion(self) -> None:
        result = LlmModel.get_orcarouter_model("gemini/gemini-2.5-flash")
        assert result == "google/gemini-2.5-flash"

    def test_vertex_ai_conversion(self) -> None:
        result = LlmModel.get_orcarouter_model("vertex_ai/gemini-2.5-flash")
        assert result == "google/gemini-2.5-flash"

    def test_deepseek_conversion(self) -> None:
        result = LlmModel.get_orcarouter_model("deepseek/deepseek-r1")
        assert result == "deepseek/deepseek-reasoner"

    def test_claude_sonnet_conversion(self) -> None:
        result = LlmModel.get_orcarouter_model("anthropic/claude-sonnet-4-5-20250929")
        assert result == "anthropic/claude-sonnet-4.5"

    def test_kimi_conversion(self) -> None:
        result = LlmModel.get_orcarouter_model("moonshot/kimi-k2.5")
        assert result == "kimi/kimi-k2.5"

    def test_llama_conversion(self) -> None:
        result = LlmModel.get_orcarouter_model("together_ai/meta-llama/llama-3.3-70b-instruct")
        assert result == "openai/gpt-4o"

    def test_grok_conversion(self) -> None:
        result = LlmModel.get_orcarouter_model("xai/grok-4-1-fast-non-reasoning")
        assert result == "grok/grok-4.3"

    def test_openai_model_unchanged(self) -> None:
        result = LlmModel.get_orcarouter_model("openai/gpt-4o")
        assert result == "openai/gpt-4o"

    def test_minimax_model_unchanged(self) -> None:
        result = LlmModel.get_orcarouter_model("minimax/minimax-m2.5")
        assert result == "minimax/minimax-m2.5"


class TestLlmModelOrcarouterIntegration:
    """Tests for LlmModel enum values with OrcaRouter methods."""

    @pytest.mark.parametrize("model", list(LlmModel))
    def test_all_models_can_be_converted_to_orcarouter(self, model: LlmModel) -> None:
        """All LlmModel values should map to a namespace served by OrcaRouter."""
        result = LlmModel.get_orcarouter_model(model.value)
        assert result.startswith(
            (
                "openai/",
                "anthropic/",
                "google/",
                "deepseek/",
                "minimax/",
                "kimi/",
                "grok/",
                "z-ai/",
                "orcarouter/",
            )
        )
