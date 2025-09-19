from dotenv import load_dotenv
from notte_sdk import NotteClient

_ = load_dotenv()


def test_new_steps():
    client = NotteClient()
    with client.Session(headless=True) as session:
        _ = session.execute(dict(type="goto", url="https://console.notte.cc"))
        _ = session.observe()

        agent = client.Agent(session=session, max_steps=1)
        _ = agent.run(task="fill this email address: hello@notte.cc")

    session_steps = session.status().steps
    agent_steps = agent.status().steps

    expected_session = (
        "execution_result",
        "observation",
        "agent_step_start",
        "observation",
        "agent_completion",
        "execution_result",
        "agent_step_stop",
    )
    expected_agent = "agent_step_start", "observation", "agent_completion", "execution_result", "agent_step_stop"
    assert len(session_steps) == len(agent_steps) + 2  # first execute and observe
    assert len(agent_steps) == len(expected_agent)
    assert session_steps[2:] == agent_steps

    for session_step, expected_step in zip(session_steps, expected_session):
        assert session_step["type"] == expected_step

    for agent_step, expected_step in zip(agent_steps, expected_agent):
        assert agent_step["type"] == expected_step

    first_action = session_steps[0]["value"].get("action")
    assert first_action is not None, f"{session_steps[1]} should have an action"
    assert first_action["type"] == "goto", f"{session_steps[1]} should a goto action"
    last_action = session_steps[-2]["value"].get("action")
    assert last_action is not None, f"{session_steps[-2]} should have an action"
    assert last_action["type"] == "fill", f"{session_steps[-2]} should a fill action"
    # shoudl be equal to the last agent step
    last_agent_action = agent_steps[-2]["value"].get("action")
    assert last_agent_action is not None, f"{agent_steps[-2]} should have an action"
    assert last_action == last_agent_action


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
