import os

import pytest
from dotenv import load_dotenv
from notte_core.llms.engine import LLMEngine, LlmModel
from pydantic import BaseModel


class Country(BaseModel):
    name: str
    capital: str


def get_models() -> list[LlmModel]:
    _ = load_dotenv()
    models: list[LlmModel] = []
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        models.append(LlmModel.gemini_vertex)
        models.append(LlmModel.gemini_2_5_vertex)
    if "OPENAI_API_KEY" in os.environ:
        models.append(LlmModel.openai)
    if "GROQ_API_KEY" in os.environ:
        models.append(LlmModel.groq)
    if "PERPLEXITY_API_KEY" in os.environ:
        models.append(LlmModel.perplexity)
    if "CEBREAS_API_KEY" in os.environ:
        models.append(LlmModel.cerebras)
    if "GEMINI_API_KEY" in os.environ:
        models.append(LlmModel.gemini)
    if "GEMMA_API_KEY" in os.environ:
        models.append(LlmModel.gemma)
    if "ANTHROPIC_API_KEY" in os.environ:
        models.append(LlmModel.anthropic)
    return models


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
