"""Manual live checks of the configured compatible endpoint; the full matrix is benchmarked separately."""

import os

import pytest
from notte_core.actions import ActionUnion, GotoAction
from notte_llm.engine import LLMEngine
from pydantic import BaseModel

pytestmark = [
    pytest.mark.live,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not (os.getenv("NOTTE_LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY")), reason="requires LLM key"
    ),
]


class Country(BaseModel):
    name: str
    capital: str


class Countries(BaseModel):
    countries: list[Country]


class ActionOutput(BaseModel):
    action: ActionUnion


@pytest.mark.parametrize("use_strict_response_format", [True, False])
async def test_structured_output(use_strict_response_format):
    result = await LLMEngine().structured_completion(
        [{"role": "user", "content": "What is the capital of France? Return JSON with name and capital."}],
        Country,
        use_strict_response_format=use_strict_response_format,
    )
    assert result.capital == "Paris"


@pytest.mark.parametrize("use_strict_response_format", [True, False])
async def test_structured_output_list(use_strict_response_format):
    result = await LLMEngine().structured_completion(
        [
            {
                "role": "user",
                "content": "List France, Germany, Spain and Italy in that order with their capitals as JSON.",
            }
        ],
        Countries,
        use_strict_response_format=use_strict_response_format,
    )
    assert [c.capital for c in result.countries] == ["Paris", "Berlin", "Madrid", "Rome"]


async def test_action_union_structured_output():
    result = await LLMEngine().structured_completion(
        [
            {
                "role": "user",
                "content": "Return a goto action for https://example.com as a JSON object with an action field.",
            }
        ],
        ActionOutput,
    )
    assert isinstance(result.action, GotoAction)
    assert result.action.url == "https://example.com"
