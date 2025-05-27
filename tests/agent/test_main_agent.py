import pytest
from notte_agent.main import Agent, AgentType


@pytest.fixture
def task():
    return "open google flights and book cheapest flight from nyc to sf"


def test_falco_agent(task: str):
    agent = Agent(agent_type=AgentType.FALCO, max_steps=5)
    assert agent is not None
    response = agent.run(task)
    assert response is not None
    assert response.success
    assert response.answer is not None
    assert response.answer != ""


@pytest.skip("Renable that later on when we fix the gufo agent")
def test_gufo_agent(task: str):
    agent = Agent(agent_type=AgentType.GUFO, max_steps=5)
    assert agent is not None
    response = agent.run(task)
    assert response is not None
    assert response.success
    assert response.answer is not None
    assert response.answer != ""
