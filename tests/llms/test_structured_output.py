import os

import pytest
from dotenv import load_dotenv
from notte_core.llms.engine import LLMEngine, LlmModel
from pydantic import BaseModel


class Country(BaseModel):
    capital: str


def get_models() -> list[LlmModel]:
    _ = load_dotenv()
    models: list[LlmModel] = []
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        models.append(LlmModel.gemini_vertex)
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
    return models


@pytest.mark.parametrize("model", get_models())
def test_structured_output(model: LlmModel):
    engine = LLMEngine(model=model)
    result = engine.structured_completion(
        messages=[{"role": "user", "content": "What is the capital of France?"}], response_format=Country
    )
    assert result is not None
    assert result.capital == "Paris"


class Countries(BaseModel):
    countries: list[Country]


@pytest.mark.parametrize("model", get_models())
def test_structured_output_list(model: LlmModel):
    engine = LLMEngine(model=model)
    result = engine.structured_completion(
        messages=[
            {
                "role": "user",
                "content": "What are the capitals of the following countries in Europe: France, Germany, Spain and Italy.",
            }
        ],
        response_format=Countries,
    )
    assert result is not None
    assert len(result.countries) == 4
    assert result.countries[0].capital == "Paris"
    assert result.countries[1].capital == "Berlin"
    assert result.countries[2].capital == "Madrid"
    assert result.countries[3].capital == "Rome"
