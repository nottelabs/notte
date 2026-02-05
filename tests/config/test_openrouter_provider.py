import pytest
from notte_core.common.config import LlmModel


class TestGetOpenrouterProvider:
    """Tests for LlmModel.get_openrouter_provider() method."""

    def test_cerebras_model_returns_cerebras(self) -> None:
        assert LlmModel.get_openrouter_provider("cerebras/gpt-oss-120b") == "Cerebras"

    def test_groq_model_returns_groq(self) -> None:
        assert LlmModel.get_openrouter_provider("groq/gpt-oss-120b") == "Groq"

    def test_together_model_returns_together(self) -> None:
        assert LlmModel.get_openrouter_provider("together_ai/meta-llama/llama-3.3-70b-instruct") == "Together"

    def test_openai_model_returns_none(self) -> None:
        assert LlmModel.get_openrouter_provider("openai/gpt-4o") is None

    def test_anthropic_model_returns_none(self) -> None:
        assert LlmModel.get_openrouter_provider("anthropic/claude-sonnet-4-5-20250929") is None

    def test_gemini_model_returns_none(self) -> None:
        assert LlmModel.get_openrouter_provider("gemini/gemini-2.5-flash") is None


class TestGetOpenrouterModel:
    """Tests for LlmModel.get_openrouter_model() method."""

    def test_already_openrouter_model_unchanged(self) -> None:
        model = "openrouter/google/gemma-3-27b-it"
        assert LlmModel.get_openrouter_model(model) == model

    def test_gpt_oss_120b_conversion(self) -> None:
        result = LlmModel.get_openrouter_model("cerebras/gpt-oss-120b")
        assert result == "openrouter/openai/gpt-oss-120b"

    def test_gemma_conversion(self) -> None:
        result = LlmModel.get_openrouter_model("some/gemma-3-27b-it")
        assert result == "openrouter/google/gemma-3-27b-it"

    def test_deepseek_conversion(self) -> None:
        result = LlmModel.get_openrouter_model("deepseek/deepseek-r1")
        assert result == "openrouter/deepseek/deepseek-r1"

    def test_claude_sonnet_conversion(self) -> None:
        result = LlmModel.get_openrouter_model("anthropic/claude-sonnet-4-5-20250929")
        assert result == "openrouter/anthropic/claude-sonnet-4-5"

    def test_vertex_ai_conversion(self) -> None:
        result = LlmModel.get_openrouter_model("vertex_ai/gemini-2.5-flash")
        assert result == "openrouter/google/gemini-2.5-flash"

    def test_gemini_prefix_conversion(self) -> None:
        result = LlmModel.get_openrouter_model("gemini/gemini-2.5-flash")
        assert result == "openrouter/google/gemini-2.5-flash"

    def test_kimi_conversion(self) -> None:
        result = LlmModel.get_openrouter_model("moonshot/kimi-k2.5")
        assert result == "openrouter/moonshotai/kimi-k2.5"

    def test_llama_conversion(self) -> None:
        result = LlmModel.get_openrouter_model("together_ai/meta-llama/llama-3.3-70b-instruct")
        assert result == "openrouter/meta-llama/llama-3.3-70b-instruct"

    def test_openai_model_adds_prefix(self) -> None:
        result = LlmModel.get_openrouter_model("openai/gpt-4o")
        assert result == "openrouter/openai/gpt-4o"


class TestLlmModelOpenrouterIntegration:
    """Tests for LlmModel enum values with OpenRouter methods."""

    @pytest.mark.parametrize(
        "model",
        [
            LlmModel.cerebras,
            LlmModel.groq,
            LlmModel.together,
        ],
    )
    def test_provider_models_have_openrouter_provider(self, model: LlmModel) -> None:
        """Models with specific providers should return a non-None provider."""
        assert LlmModel.get_openrouter_provider(model.value) is not None

    @pytest.mark.parametrize("model", list(LlmModel))
    def test_all_models_can_be_converted_to_openrouter(self, model: LlmModel) -> None:
        """All LlmModel values should be convertible to OpenRouter format."""
        result = LlmModel.get_openrouter_model(model.value)
        assert result.startswith("openrouter/")
