import pytest
from dotenv import load_dotenv
from notte_core.common.config import LlmModel
from notte_sdk.client import NotteClient

_ = load_dotenv()


def test_agent_fallback():
    client = NotteClient()
    with client.Session(headless=True) as session:
        _ = session.execute({"type": "goto", "url": "https://www.allrecipes.com/"})
        _ = session.execute({"type": "click", "selector": "~ Accept All"}, raise_on_failure=False)
        _ = session.observe()
        with client.AgentFallback(
            session,
            task="find the best apple crumble recipe on the site",
            max_steps=3,
            reasoning_model=LlmModel.cerebras,
            use_vision=False,
        ) as agent_fallback:
            _ = session.execute({"type": "fill", "id": "I1", "value": "apple crumble"})
            _ = session.execute({"type": "click", "id": "B1332498"})

        agent = agent_fallback._agent  # pyright: ignore [reportPrivateUsage]
        assert agent is not None

        # ensure the first step is click
        # meaning the agent remembers already filling the field
        status = agent.status()
        step = status.steps[3]
        action = step["value"].get("action")
        assert action is not None, f"Expected action, got {step} with type sequence {[s['type'] for s in status.steps]}"
        assert action["type"] == "click", f"Expected click, got {action}"
        assert action["id"] == "B1" or action["id"] == "B3"


def test_agent_fallback_scrape_should_raise_error():
    client = NotteClient()
    with client.Session(headless=True) as session:
        _ = session.execute({"type": "goto", "url": "https://www.allrecipes.com/"})

        with pytest.raises(ValueError):
            with client.AgentFallback(session, task="find the best apple crumble recipe on the site", max_steps=1):
                _ = session.scrape()
