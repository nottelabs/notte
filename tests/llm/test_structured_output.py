import os

import pytest
from dotenv import load_dotenv
from notte_core.actions import ActionUnion, GotoAction
from notte_llm.engine import LLMEngine
from notte_llm.models import LlmModel, enable_openrouter
from pydantic import BaseModel


class Country(BaseModel):
    name: str
    capital: str


def get_models() -> list[LlmModel]:
    _ = load_dotenv()
    if enable_openrouter():
        # enable all models
        return list(LlmModel)
    models: list[LlmModel] = []
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        models.append(LlmModel.gemini_vertex)
    if "OPENAI_API_KEY" in os.environ:
        models.append(LlmModel.openai)
    if "GROQ_API_KEY" in os.environ:
        models.append(LlmModel.groq)
    if "PERPLEXITY_API_KEY" in os.environ:
        models.append(LlmModel.perplexity)
    if "CEREBRAS_API_KEY" in os.environ:
        models.append(LlmModel.cerebras)
    if "GEMINI_API_KEY" in os.environ:
        models.append(LlmModel.gemini)
    if "GEMMA_API_KEY" in os.environ:
        models.append(LlmModel.gemma)
    if "ANTHROPIC_API_KEY" in os.environ:
        models.append(LlmModel.anthropic)
    if "MOONSHOT_API_KEY" in os.environ:
        models.append(LlmModel.kimi2_5)
    return models


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.parametrize("use_strict_response_format", [True, False])
@pytest.mark.parametrize("model", get_models())
async def test_structured_output(model: LlmModel, use_strict_response_format: bool):
    if model == LlmModel.perplexity and not use_strict_response_format:
        pytest.skip("Perplexity only supports strict response format")
    engine = LLMEngine(model=model)
    result = await engine.structured_completion(
        messages=[
            {
                "role": "user",
                "content": f"What is the capital of France? You should respond with a JSON object with format ```json\n{Country(name='my_country', capital='my_capital')}\n```\n",
            }
        ],
        response_format=Country,
        use_strict_response_format=use_strict_response_format,
    )
    assert result is not None
    assert result.capital == "Paris"


class Countries(BaseModel):
    countries: list[Country]


@pytest.mark.parametrize("use_strict_response_format", [True, False])
@pytest.mark.parametrize("model", get_models())
@pytest.mark.asyncio
async def test_structured_output_list(model: LlmModel, use_strict_response_format: bool):
    if model == LlmModel.perplexity and not use_strict_response_format:
        pytest.skip("Perplexity only supports strict response format")
    engine = LLMEngine(model=model)
    result = await engine.structured_completion(
        messages=[
            {
                "role": "user",
                "content": f"What are the capitals of the following countries in Europe: France, Germany, Spain and Italy. You should respond with a JSON object with format ```json\n{Countries(countries=[Country(name='my_country', capital='my_capital'), Country(name='my_country', capital='my_capital'), Country(name='my_country', capital='my_capital'), Country(name='my_country', capital='my_capital')])}```\n",
            }
        ],
        response_format=Countries,
        use_strict_response_format=use_strict_response_format,
    )
    assert result is not None
    assert len(result.countries) == 4
    assert result.countries[0].capital == "Paris"
    assert result.countries[1].capital == "Berlin"
    assert result.countries[2].capital == "Madrid"
    assert result.countries[3].capital == "Rome"


class ActionOutput(BaseModel):
    action: ActionUnion


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.parametrize("model", [model for model in get_models() if model in (LlmModel.anthropic, LlmModel.groq)])
async def test_action_union_structured_output(model: LlmModel):
    """Exercise provider schema support with v2's live action union instead of deleted agent models."""
    result = await LLMEngine(model=model).structured_completion(
        messages=[
            {
                "role": "user",
                "content": 'Return a goto action for https://example.com as {"action": {"type": "goto", "url": "https://example.com"}}',
            }
        ],
        response_format=ActionOutput,
    )
    assert isinstance(result.action, GotoAction)
    assert result.action.url == "https://example.com"


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif("GROQ_API_KEY" not in os.environ, reason="GROQ_API_KEY not set")
async def test_groq_public_model_name_on_direct_calls(monkeypatch: pytest.MonkeyPatch):
    # The public `groq/gpt-oss-120b` value must reach Groq directly, without OpenRouter remapping it.
    monkeypatch.setattr("notte_llm.engine.enable_openrouter", lambda: False)
    engine = LLMEngine(model=LlmModel.groq)
    result = await engine.structured_completion(
        messages=[
            {
                "role": "user",
                "content": f"What is the capital of France? You should respond with a JSON object with format ```json\n{Country(name='my_country', capital='my_capital')}\n```\n",
            }
        ],
        response_format=Country,
    )
    assert result.capital == "Paris"
