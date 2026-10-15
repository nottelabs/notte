import os
from enum import StrEnum

_enable_openrouter: bool | None = None


def enable_openrouter() -> bool:
    global _enable_openrouter
    if _enable_openrouter is not None:
        return _enable_openrouter
    _enable_openrouter = os.environ.get("ENABLE_OPENROUTER", "false").lower() in ("true", "1", "yes")
    return _enable_openrouter


class LlmProvider(StrEnum):
    openai = "openai"
    gemini = "gemini"
    vertex_ai = "vertex_ai"
    openrouter = "openrouter"
    cerebras = "cerebras"
    groq = "groq"
    perplexity = "perplexity"
    deepseek = "deepseek"
    ollama = "ollama"
    together = "together_ai"
    anthropic = "anthropic"
    moonshot = "moonshot"
    xai = "xai"
    zai = "zai"
    qwen = "qwen"
    minimax = "minimax"

    @property
    def context_length(self) -> int:
        match self:
            case LlmProvider.cerebras:
                return 16_000
            case LlmProvider.groq:
                return 8_000
            case LlmProvider.perplexity:
                return 64_000
            case _:
                return 128_000

    @property
    def apikey_name(self) -> str:
        if enable_openrouter():
            return "OPENROUTER_API_KEY"
        match self:
            case LlmProvider.gemini:
                return "GEMINI_API_KEY"
            case LlmProvider.vertex_ai:
                return "GOOGLE_APPLICATION_CREDENTIALS"
            case LlmProvider.openai:
                return "OPENAI_API_KEY"
            case LlmProvider.groq:
                return "GROQ_API_KEY"
            case LlmProvider.perplexity:
                return "PERPLEXITY_API_KEY"
            case LlmProvider.cerebras:
                return "CEREBRAS_API_KEY"
            case LlmProvider.openrouter:
                return "OPENROUTER_API_KEY"
            case LlmProvider.deepseek:
                return "DEEPSEEK_API_KEY"
            case LlmProvider.ollama:
                return "OLLAMA_API_KEY"
            case LlmProvider.anthropic:
                return "ANTHROPIC_API_KEY"
            case LlmProvider.together:
                return "TOGETHERAI_API_KEY"
            case LlmProvider.moonshot:
                return "MOONSHOT_API_KEY"
            case LlmProvider.xai:
                return "XAI_API_KEY"
            case LlmProvider.zai:
                return "ZAI_API_KEY"
            case LlmProvider.qwen:
                return "QWEN_API_KEY"
            case LlmProvider.minimax:
                return "MINIMAX_API_KEY"
            case _:  # pyright: ignore[reportUnnecessaryComparison]
                raise ValueError(f"No API key name found for provider: {self}")  # pyright: ignore[reportUnreachable]

    def has_apikey_in_env(self) -> bool:
        if self == LlmProvider.ollama:
            return True
        return os.getenv(self.apikey_name) is not None


class LlmModel(StrEnum):
    openai = "openai/gpt-4o"
    gemini = "gemini/gemini-3.5-flash"
    gemini_vertex = "vertex_ai/gemini-3.5-flash"
    gemma = "openrouter/google/gemma-3-27b-it"
    cerebras = "cerebras/gpt-oss-120b"
    groq = "groq/gpt-oss-120b"
    perplexity = "perplexity/sonar-pro"
    deepseek = "deepseek/deepseek-r1"
    together = "together_ai/meta-llama/llama-3.3-70b-instruct"
    anthropic = "anthropic/claude-sonnet-4-5-20250929"
    kimi2_5 = "moonshot/kimi-k2.5"
    grok = "xai/grok-4.3"
    minimax = "minimax/minimax-m2.5"

    @property
    def provider(self) -> LlmProvider:
        return self.get_provider(self.value)

    @staticmethod
    def get_provider(model: str) -> LlmProvider:
        provider_str = model.split("/")[0]

        if provider_str not in list(LlmProvider):
            raise ValueError(f"Invalid provider: {provider_str}")
        return LlmProvider(provider_str)

    @staticmethod
    def get_openrouter_provider(model: str) -> str | None:
        if "cerebras/" in model:
            return "Cerebras"
        if "groq/" in model:
            return "Groq"
        if "together_ai/" in model:
            return "Together"
        return None

    @staticmethod
    def get_openrouter_model(model: str) -> str:
        if model.startswith("openrouter/"):
            return model

        _model = model
        if "/gpt-oss-120b" in _model:
            _model = "openai/gpt-oss-120b"

        if "/gemma-3-27b-it" in _model:
            _model = "google/gemma-3-27b-it"

        if "/deepseek-r1" in _model:
            _model = "deepseek/deepseek-r1"

        if "/claude-sonnet-4-5" in _model:
            _model = "anthropic/claude-sonnet-4-5"

        if "vertex_ai/" in _model:
            _model = _model.replace("vertex_ai", "google")

        if "gemini/" in _model:
            _model = _model.replace("gemini/", "google/")

        if "/kimi-k2.5" in _model:
            _model = "moonshotai/kimi-k2.5"

        if "/llama-3.3-70b-instruct" in _model:
            _model = "meta-llama/llama-3.3-70b-instruct"

        if "/grok-4-1-fast-non-reasoning" in _model:
            # Legacy public value: xAI retired grok-4.1-fast and recommends 4.3
            _model = "x-ai/grok-4.3"
        elif "xai/" in _model:
            _model = _model.replace("xai/", "x-ai/")

        if "zai/" in _model:
            _model = _model.replace("zai/", "z-ai/")

        return f"openrouter/{_model}"

    @property
    def context_length(self) -> int:
        return self.provider.context_length

    @staticmethod
    def get_direct_model(model: str) -> str:
        """Model id for direct (non-OpenRouter) provider calls."""
        # Groq serves gpt-oss under the openai/ namespace; the public value omits it.
        if model == "groq/gpt-oss-120b":
            return "groq/openai/gpt-oss-120b"
        return model

    @staticmethod
    def use_strict_response_format(val: "str | LlmModel") -> bool:
        val_str = str(val)
        # Providers that don't support strict response format or have schema size limits
        unsupported_providers = [
            str(LlmProvider.cerebras),
            str(LlmProvider.moonshot),
        ]
        unsupported_models = [
            "gemini-2.0-flash",
        ]
        return not any(val_str.startswith(p) for p in unsupported_providers) and not any(
            m in val_str for m in unsupported_models
        )

    @staticmethod
    def get_temperature(val: "str | LlmModel", default: float) -> float:
        """Get the temperature for a model, with model-specific overrides."""
        val_str = str(val)
        # Model-specific temperature overrides
        temperature_overrides: dict[str, float] = {
            "kimi-k2.5": 1.0,
        }
        for model_pattern, temp in temperature_overrides.items():
            if model_pattern in val_str:
                return temp
        return default

    @staticmethod
    def default() -> "LlmModel":
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            return LlmModel.gemini_vertex
        return LlmModel.gemini

    @staticmethod
    def valid() -> set[str]:
        return {model.value for model in LlmModel if model.provider.has_apikey_in_env()}
