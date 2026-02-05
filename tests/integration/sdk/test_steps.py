import time

import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient

_ = load_dotenv()


def test_new_steps():
    client = NotteClient()
    with client.Session(open_viewer=False) as session:
        _ = session.execute(type="goto", url="https://phantombuster.com/login")
        _ = session.observe()

        # max_steps=2 to handle cookie consent banner before filling email
        agent = client.Agent(session=session, max_steps=2)
        _ = agent.run(task="fill this email address: hello@notte.cc")

    session_steps = session.status().steps
    agent_steps = agent.status().steps

    # First two session steps are from manual execute(goto) and observe()
    assert session_steps[0]["type"] == "execution_result"
    assert session_steps[1]["type"] == "observation"
    # Agent steps should be a suffix of session steps (after the initial goto + observe)
    assert session_steps[2:] == agent_steps

    # Check first action is goto
    first_action = session_steps[0]["value"].get("action")
    assert first_action is not None, f"{session_steps[0]} should have an action"
    assert first_action["type"] == "goto", "First action should be goto"

    # Find the last execution_result with an action (skip agent_step_stop)
    execution_results = [s for s in session_steps if s["type"] == "execution_result" and s["value"].get("action")]
    assert len(execution_results) >= 2, "Should have at least 2 execution results (goto + fill)"

    last_action = execution_results[-1]["value"]["action"]
    assert last_action["type"] == "fill", f"Last action should be fill, got {last_action['type']}"

    # Verify the last agent execution_result matches
    agent_execution_results = [s for s in agent_steps if s["type"] == "execution_result" and s["value"].get("action")]
    assert len(agent_execution_results) >= 1, "Agent should have at least 1 execution result"
    assert agent_execution_results[-1]["value"]["action"] == last_action


@pytest.mark.skip(reason="no old session format after migration")
def test_new_session_format():
    client = NotteClient()

    session_id = "33c3c8bf-9d6d-4dff-8248-142eaf347f59"
    agent_id = "d3eeb68a-4a47-409c-8212-0073c1571f18"

    session_steps = client.Session(session_id=session_id).status().steps
    agent_steps = client.Agent(agent_id=agent_id).status().steps

    expected_session = "execution_result", "observation", "observation", "agent_completion", "execution_result"
    assert len(session_steps) == len(expected_session)
    assert len(agent_steps) == 1  # 1 completion call

    for session_step, expected_step in zip(session_steps, expected_session):
        assert session_step["type"] == expected_step

    assert session_steps[0]["value"]["action"]["type"] == "goto"
    assert session_steps[-1]["value"]["action"]["type"] == "fill"
    assert agent_steps[0]["action"]["type"] == "fill"


@pytest.mark.skip(reason="no old session format after migration")
def test_old_session_format():
    client = NotteClient()

    session_id = "0ce42688-7afc-4abb-b761-74b58334e4e7"

    session_steps = client.Session(session_id=session_id).status().steps

    expected_session = "execution_result", "execution_result", "execution_result"

    assert len(session_steps) == len(expected_session)

    for session_step, expected_step in zip(session_steps, expected_session):
        assert session_step["type"] == expected_step

    assert session_steps[0]["value"]["action"]["type"] == "goto"
    assert session_steps[1]["value"]["action"]["type"] == "goto"
    assert session_steps[2]["value"]["action"]["type"] == "click"


def test_agents_in_single_session():
    client = NotteClient()
    with client.Session(browser_type="chrome", open_viewer=False) as session:
        agent1 = client.Agent(session=session, max_steps=1)
        _ = agent1.run(task="go to linkedin", url="https://www.linkedin.com")

        agent2 = client.Agent(session=session, max_steps=1)
        _ = agent2.run(task="go to notte", url="https://www.notte.cc")

        agent3 = client.Agent(session=session, max_steps=1)
        _ = agent3.run(task="go to reddit", url="https://www.reddit.com")

        # Get agent step counts FIRST (they know their own steps immediately)
        agent_1_steps = len(agent1.status().steps)
        agent_2_steps = len(agent2.status().steps)
        agent_3_steps = len(agent3.status().steps)
        expected_total = agent_1_steps + agent_2_steps + agent_3_steps

        # Session status called LAST with retry for eventual consistency
        # (steps may be written asynchronously to the database)
        session_steps = 0
        for _ in range(5):
            session_steps = len(session.status().steps)
            if session_steps >= expected_total:
                break
            time.sleep(0.3)

        assert session_steps == expected_total, (
            f"Session steps ({session_steps}) != sum of agent steps ({expected_total})"
        )
        assert agent_1_steps == agent_2_steps
        assert agent_2_steps == agent_3_steps
