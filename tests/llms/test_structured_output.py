import os

import pytest
from dotenv import load_dotenv
from notte_core.actions import CompletionAction
from notte_core.agent_types import AgentCompletion, AgentState
from notte_core.common.config import LlmModel, enable_openrouter
from notte_llm.engine import LLMEngine
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


def get_agent_action_models() -> list[LlmModel]:
    # Anthropic rejects the agent action schema in strict mode on recent litellm, exercising the json_object fallback.
    return [model for model in get_models() if model == LlmModel.anthropic]


@pytest.mark.asyncio
@pytest.mark.parametrize("model", get_agent_action_models())
async def test_agent_action_structured_output(model: LlmModel):
    example = AgentCompletion.InnerLlmCompletion(
        state=AgentState(
            previous_goal_status="success",
            previous_goal_eval="Task can be finished",
            page_summary="Empty page",
            relevant_interactions=[],
            memory="Nothing to remember",
            next_goal="Finish the task",
        ),
        action=CompletionAction(success=True, answer="done"),
    )
    engine = LLMEngine(model=model)
    result = await engine.structured_completion(
        messages=[
            {
                "role": "user",
                "content": (
                    "You are a browser agent. The task is already complete: return a `completion` action with "
                    f"success=true and answer 'done'. Respond with a JSON object like:\n```json\n{example.model_dump_json()}\n```\n"
                ),
            }
        ],
        response_format=AgentCompletion.InnerLlmCompletion,
    )
    assert isinstance(result.action, CompletionAction)
    assert result.action.success


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
