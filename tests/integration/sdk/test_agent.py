import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient


def test_start_stop_agent():
    _ = load_dotenv()
    notte = NotteClient()
    with notte.Session() as session:
        agent = notte.Agent(session=session, max_steps=10)
        _ = agent.start(task="Go to google image and dom scrool cat memes")
        resp = agent.status()
        assert resp.status == "active"
        _ = agent.stop()
        resp = agent.status()
        assert resp.status == "closed"
        assert not resp.success


def test_agent_ff():
    _ = load_dotenv()
    notte = NotteClient()
    with notte.Session(browser_type="firefox") as session:
        agent = notte.Agent(session=session, max_steps=3)
        _ = agent.run(task="Go to google image and find a dog picture")


@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_start_agent_with_gemini_reasoning():
    _ = load_dotenv()
    notte = NotteClient()
    with notte.Session() as session:
        agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=3)
        _ = agent.run(task="Go notte.cc and describe the page")
    resp = agent.status()
    assert resp.status == "closed"
    assert resp.success
