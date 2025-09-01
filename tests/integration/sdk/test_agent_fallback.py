from notte_sdk.client import NotteClient


def test_agent_fallback():
    client = NotteClient()
    with client.Session(headless=True) as session:
        _ = session.execute({"type": "goto", "url": "https://www.allrecipes.com/"})
        _ = session.observe()
        with client.AgentFallback(session, task="find the best apple crumble recipe on the site") as agent_fallback:
            _ = session.execute({"type": "fill", "id": "I1", "value": "apple crumble"})
            _ = session.execute({"type": "click", "id": "B1332498"})

        agent = agent_fallback._agent  # pyright: ignore [reportPrivateUsage]
        assert agent is not None

        # ensure the first step is click
        # meaning the agent remembers already filling the field
        status = agent.status()
        steps = status.steps
        assert steps[0]["action"]["type"] == "click"
        assert steps[0]["action"]["id"] == "B1" or steps[0]["action"]["id"] == "B3"
