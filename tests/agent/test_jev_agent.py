from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from notte_agent.jev.agent import DONE, JevAgent
from notte_agent.main import Agent, AgentType
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction, CompletionAction
from notte_core.agent_types import AgentCompletion, AgentState
from notte_llm.decision import (
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionEngine,
    DecisionModelError,
    DecisionQuestion,
    DecisionResponse,
    DecisionUsage,
    NoulAnswer,
    NoulQuestion,
)

from tests.agent.test_consistent_trajectory import MockLLMEngine, MockValidator

QUESTIONS: dict[str, DecisionQuestion] = {
    "next": ChoiceQuestion(instructions="which one?", criteria={"L1": "click 'a'", "DONE": "done"}),
    "done": NoulQuestion(instructions="is it done?"),
}


class MockDecisionEngine:
    """Mock decision engine: `policy` maps the choice criteria to (choice, confidence, done)"""

    def __init__(self, policy: Any):
        self.policy: Any = policy
        self.nb_calls: int = 0
        self.usage: DecisionUsage = DecisionUsage()
        self.states: list[Any] = []

    async def decide(self, state: Any, questions: dict[str, DecisionQuestion]) -> DecisionResponse:
        self.nb_calls += 1
        self.states.append(state)
        question = questions["next"]
        assert isinstance(question, ChoiceQuestion)
        choice, confidence, done = self.policy(question.criteria, self.nb_calls)
        return DecisionResponse(
            model="mock",
            answers={
                "next": ChoiceAnswer(choice=choice, probabilities={choice: confidence}, confidence=confidence),
                "done": NoulAnswer(noul=done),
            },
        )


def llm_completion() -> Any:
    return AgentCompletion.InnerLlmCompletion(
        state=AgentState(
            previous_goal_status="success",
            previous_goal_eval="Opened the link",
            page_summary="Final page reached",
            relevant_interactions=[],
            memory="Task completed",
            next_goal="Complete the task",
        ),
        action=CompletionAction(success=True, answer="Task completed successfully"),
    )


def first_link(criteria: dict[str, str]) -> str:
    return next(option for option, desc in criteria.items() if desc.startswith("click") and option.startswith("L"))


def make_agent(session: NotteSession, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> JevAgent:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")  # pragma: allowlist secret
    return JevAgent(session=session, max_steps=5, **kwargs)


def test_agent_type_jev(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")  # pragma: allowlist secret
    with NotteSession(headless=True) as session:
        agent = Agent(session=session, agent_type=AgentType.JEV).create_agent()
        assert isinstance(agent, JevAgent)


@pytest.mark.asyncio
async def test_confident_click_bypasses_llm(monkeypatch: pytest.MonkeyPatch):
    def policy(criteria: dict[str, str], nb_calls: int) -> tuple[str, float, float]:
        if nb_calls == 1:
            return first_link(criteria), 0.99, 0.02
        return DONE, 0.99, 0.98

    mock_llm, mock_decision = MockLLMEngine([llm_completion()]), MockDecisionEngine(policy)
    async with NotteSession(headless=True) as session:
        agent = make_agent(session, monkeypatch)
        with (
            patch.object(agent, "llm", mock_llm),
            patch.object(agent, "validator", MockValidator()),
            patch.object(agent, "decision", mock_decision),
        ):
            response = await agent.arun(task="Open the first link", url="https://example.com")

    assert response.success
    completions = list(response.trajectory.agent_completions())
    # initial goto + decision model click + llm completion
    assert [c.action.type for c in completions] == ["goto", "click", "completion"]
    assert isinstance(completions[1].action, ClickAction)
    assert "decision model" in completions[1].state.next_goal
    assert isinstance(completions[2].action, CompletionAction)
    assert agent.nb_decision_steps == 1
    assert dict(agent.fallback_reasons) == {"task completion": 1}
    assert mock_decision.states[0]["task"] == "Open the first link"
    assert "example" in mock_decision.states[0]["page"].lower()


@pytest.mark.asyncio
async def test_low_confidence_falls_back_to_llm(monkeypatch: pytest.MonkeyPatch):
    def policy(criteria: dict[str, str], nb_calls: int) -> tuple[str, float, float]:
        return first_link(criteria), 0.4, 0.02

    mock_llm, mock_decision = MockLLMEngine([llm_completion()]), MockDecisionEngine(policy)
    async with NotteSession(headless=True) as session:
        agent = make_agent(session, monkeypatch)
        with (
            patch.object(agent, "llm", mock_llm),
            patch.object(agent, "validator", MockValidator()),
            patch.object(agent, "decision", mock_decision),
        ):
            response = await agent.arun(task="Open the first link", url="https://example.com")

    assert response.success
    assert agent.nb_decision_steps == 0
    assert dict(agent.fallback_reasons) == {"low confidence": 1}
    assert [c.action.type for c in response.trajectory.agent_completions()] == ["goto", "completion"]


@pytest.mark.asyncio
async def test_decision_error_falls_back_to_llm(monkeypatch: pytest.MonkeyPatch):
    def policy(criteria: dict[str, str], nb_calls: int) -> tuple[str, float, float]:
        raise DecisionModelError("boom")

    async with NotteSession(headless=True) as session:
        agent = make_agent(session, monkeypatch)
        with (
            patch.object(agent, "llm", MockLLMEngine([llm_completion()])),
            patch.object(agent, "validator", MockValidator()),
            patch.object(agent, "decision", MockDecisionEngine(policy)),
        ):
            response = await agent.arun(task="Open the first link", url="https://example.com")

    assert response.success
    assert dict(agent.fallback_reasons) == {"decision model error": 1}


def mock_post(status_code: int, payload: dict[str, Any]) -> AsyncMock:
    request = httpx.Request("POST", "https://openrouter.ai/api/alpha/decisions")
    return AsyncMock(return_value=httpx.Response(status_code, json=payload, request=request))


@pytest.mark.asyncio
async def test_decision_engine_parses_answers():
    payload = {
        "model": "typesafe/jev-1.13",
        "answers": {
            "next": {"type": "choice", "choice": "L1", "probabilities": {"L1": 0.9, "DONE": 0.1}, "confidence": 0.8},
            "done": {"type": "noul", "noul": 0.05},
        },
        "usage": {"input_tokens": 100, "output_tokens": 10, "cost": 0.001},
    }
    engine = DecisionEngine(api_key="test-key")  # pragma: allowlist secret
    with patch.object(httpx.AsyncClient, "post", mock_post(200, payload)) as post:
        response = await engine.decide(state={"task": "t"}, questions=QUESTIONS)
        response = await engine.decide(state={"task": "t"}, questions=QUESTIONS)

    assert post.call_args.kwargs["json"]["questions"]["next"]["criteria"] == {"L1": "click 'a'", "DONE": "done"}
    assert response.choice("next").top(1) == [("L1", 0.9)]
    assert response.noul("done") == 0.05
    assert engine.nb_calls == 2
    assert engine.usage.input_tokens == 200
    with pytest.raises(DecisionModelError):
        _ = response.noul("next")


@pytest.mark.asyncio
async def test_decision_engine_errors():
    engine = DecisionEngine(api_key="test-key")  # pragma: allowlist secret
    with patch.object(httpx.AsyncClient, "post", mock_post(400, {"error": {"message": "bad request"}})):
        with pytest.raises(DecisionModelError):
            _ = await engine.decide(state="s", questions=QUESTIONS)
    with patch.object(httpx.AsyncClient, "post", mock_post(200, {"model": "m", "answers": {}})):
        with pytest.raises(DecisionModelError):
            _ = await engine.decide(state="s", questions=QUESTIONS)


def test_decision_engine_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError):
        _ = DecisionEngine()
