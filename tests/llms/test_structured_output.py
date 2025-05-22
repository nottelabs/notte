import pytest
from notte_core.llms.engine import LLMEngine, LlmModel
from pydantic import BaseModel


class Country(BaseModel):
    capital: str


@pytest.mark.skip(reason="The CICD does not have all API keys")
@pytest.mark.parametrize("model", [model for model in list(LlmModel)])
def test_structured_output(model: LlmModel):
    engine = LLMEngine(model=model)
    result = engine.structured_completion(
        messages=[{"role": "user", "content": "What is the capital of France?"}], response_format=Country
    )
    assert result is not None
    assert result.capital == "Paris"


class Countries(BaseModel):
    countries: list[Country]


@pytest.mark.skip(reason="The CICD does not have all API keys")
@pytest.mark.parametrize("model", [model for model in list(LlmModel)])
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
