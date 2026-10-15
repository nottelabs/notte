import json

import httpx
import pytest
from notte_llm.engine import OPENROUTER_FALLBACK_MODELS, LLMEngine


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base_url,is_openrouter",
    [
        ("https://openrouter.ai/api/v1", True),
        ("https://openrouter.ai/custom", True),
        ("https://api.openai.com/v1", False),
        ("https://openrouter.ai.example.com/v1", False),
        ("http://localhost:11434/v1", False),
    ],
)
async def test_extras_are_only_sent_to_openrouter_host(base_url, is_openrouter, monkeypatch):
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", base_url)
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": []})

    engine = LLMEngine(
        model="vendor/native-model",
        transport=httpx.MockTransport(handler),
        provider_order=["Together"],
        reasoning={"enabled": False},
    )
    await engine.completion([])
    body = bodies[0]
    assert body["model"] == "vendor/native-model"
    if is_openrouter:
        assert body["models"] == ["vendor/native-model", *OPENROUTER_FALLBACK_MODELS]
        assert body["provider"] == {"order": ["Together"], "allow_fallbacks": True}
        assert body["reasoning"] == {"enabled": False}
    else:
        assert not {"models", "provider", "reasoning"} & body.keys()


def test_fallback_list_does_not_repeat_requested_model(monkeypatch):
    monkeypatch.delenv("NOTTE_LLM_BASE_URL", raising=False)
    engine = LLMEngine(model=OPENROUTER_FALLBACK_MODELS[0])
    assert engine._get_extra_body(None)["models"] == list(OPENROUTER_FALLBACK_MODELS)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["openai/gpt-4o", "google/gemini-3.5-flash", "moonshotai/kimi-k2.5", "native-name"])
async def test_model_and_temperature_are_passed_without_translation(model, monkeypatch):
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")

    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == model
        assert body["temperature"] == 0.25
        return httpx.Response(200, json={"choices": []})

    await LLMEngine(model=model, transport=httpx.MockTransport(handler)).completion([], temperature=0.25)
