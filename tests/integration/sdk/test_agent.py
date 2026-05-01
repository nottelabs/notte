import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient

import notte


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
    with notte.Session(browser_type="chrome") as session:
        agent = notte.Agent(session=session, max_steps=3)
        _ = agent.run(task="Go to google image and find a dog picture")


@pytest.mark.flaky(reruns=3, reruns_delay=5)
def test_agent_gemini_form_fill_no_null_fields():
    """Gemini should only fill requested fields, not all fields with null."""
    _ = load_dotenv()
    client = NotteClient()
    with client.Session() as session:
        agent = client.Agent(session=session, max_steps=3, reasoning_model="vertex_ai/gemini-2.5-flash")
        response = agent.run(
            task="Ignore the web page. Simply return a form fill action with email='lucas@notte.cc' and password='123456'. Stop immediately after this",
            url="https://github.com/login",
        )
        # response.success is sufficient: without the null-stripping fix in FormFillAction,
        # Gemini returns all 26 form fields with null values, which fails Pydantic validation
        # and causes the agent run to fail.
        assert response.success


@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_local_agent_gemini_form_fill_no_null_fields():
    """Local agent: Gemini should only fill requested fields, not all fields with null."""
    _ = load_dotenv()
    with notte.Session(headless=True) as session:
        agent = notte.Agent(session=session, max_steps=3, reasoning_model="vertex_ai/gemini-2.5-flash")
        response = agent.run(
            task="Ignore the web page. Simply return a form fill action with email='lucas@notte.cc' and password='123456'. Stop immediately after this",
            url="https://console.notte.cc/login",
        )
        # response.success is sufficient: without the null-stripping fix in FormFillAction,
        # Gemini returns all 26 form fields with null values, which fails Pydantic validation
        # and causes the agent run to fail.
        assert response.success


@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_start_agent_with_gemini_reasoning():
    _ = load_dotenv()
    notte = NotteClient()
    with notte.Session() as session:
        agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.0-flash-001", max_steps=3)
        _ = agent.run(task="Go notte.cc and describe the page")
    resp = agent.status()
    assert resp.status == "closed"
    assert resp.success
