import time
from typing import Any

import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient

_ = load_dotenv()


AGENT_STEP_LAYOUT = ["agent_step_start", "observation", "agent_completion", "execution_result", "agent_step_stop"]


def agent_step_blocks(steps: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split a flat step list into one block per agent step (each opened by an agent_step_start)."""
    blocks: list[list[dict[str, Any]]] = []
    for step in steps:
        if step["type"] == "agent_step_start":
            blocks.append([])
        assert blocks, f"step {step['type']} recorded before any agent_step_start"
        blocks[-1].append(step)
    return blocks


@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_new_steps():
    client = NotteClient()
    with client.Session(proxies=False, open_viewer=False) as session:
        _ = session.execute(type="goto", url="https://phantombuster.com/login")
        _ = session.observe()

        # Two steps: the fill, then the agent's completion. If a cookie-consent banner
        # shows up the agent spends the first step dismissing it and the second on the
        # fill, and the run ends on max_steps without a completion.
        agent = client.Agent(session=session, max_steps=2)
        response = agent.run(task="fill this email address: hello@notte.cc")

    session_steps = session.status().steps
    agent_steps = agent.status().steps

    # First two session steps are from the manual execute(goto) and observe()
    assert session_steps[0]["type"] == "execution_result"
    assert session_steps[0]["value"]["action"]["type"] == "goto", "First action should be goto"
    assert session_steps[1]["type"] == "observation"
    # Agent steps are the suffix of the session steps after the initial goto + observe
    assert session_steps[2:] == agent_steps

    # Every agent step is recorded as start / observation / agent_completion / execution_result / stop,
    # and the executed action is the one the agent proposed in its completion.
    blocks = agent_step_blocks(agent_steps)
    assert 1 <= len(blocks) <= 2, f"Expected 1 or 2 agent steps, got {len(blocks)}"
    for block in blocks:
        assert [s["type"] for s in block] == AGENT_STEP_LAYOUT, [s["type"] for s in block]
        proposed = block[2]["value"]["action"]
        executed = block[3]["value"]["action"]
        assert executed["type"] == proposed["type"], (
            f"executed {executed['type']} but agent proposed {proposed['type']}"
        )

    results = [block[3]["value"] for block in blocks]
    executed_types = [r["action"]["type"] for r in results]

    # The task itself: exactly one successful fill of the requested email
    fills = [r for r in results if r["action"]["type"] == "fill"]
    assert len(fills) == 1, f"Expected exactly one fill, got {executed_types}"
    assert fills[0]["success"] is True
    assert fills[0]["action"]["value"] == "hello@notte.cc"

    if response.success:
        # The agent finished: its validated completion is recorded as the last execution_result,
        # right after the fill.
        assert executed_types[-2:] == ["fill", "completion"], executed_types
        assert results[-1]["success"] is True
        assert results[-1]["action"]["success"] is True
    else:
        # Ran out of steps (e.g. a cookie banner took the first one): the fill is the last action
        assert executed_types[-1] == "fill", executed_types


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
    with client.Session(proxies=False, browser_type="chrome", open_viewer=False) as session:
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
