import pytest
from dotenv import load_dotenv
from notte_sdk.client import NotteClient

_ = load_dotenv()


def test_agent_fallback():
    client = NotteClient()
    with client.Session(headless=True) as session:
        _ = session.execute({"type": "goto", "url": "https://www.allrecipes.com/"})
        _ = session.execute({"type": "click", "selector": "~ Accept All"}, raise_on_failure=False)
        _ = session.observe()
        with client.AgentFallback(
            session, task="find the best apple crumble recipe on the site", max_steps=3
        ) as agent_fallback:
            _ = session.execute({"type": "fill", "id": "I1", "value": "apple crumble"})
            _ = session.execute({"type": "click", "id": "B1332498"})

        agent = agent_fallback._agent  # pyright: ignore [reportPrivateUsage]
        assert agent is not None

        # ensure the first step is click
        # meaning the agent remembers already filling the field
        status = agent.status()
        steps = status.steps
        assert steps[1]["action"]["type"] == "click"
        assert steps[1]["action"]["id"] == "B1" or steps[1]["action"]["id"] == "B3"


def test_agent_fallback_scrape_should_raise_error():
    client = NotteClient()
    with client.Session(headless=True) as session:
        _ = session.execute({"type": "goto", "url": "https://www.allrecipes.com/"})

        with pytest.raises(ValueError):
            with client.AgentFallback(session, task="find the best apple crumble recipe on the site", max_steps=1):
                _ = session.scrape()
