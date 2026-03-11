import pytest
from dotenv import load_dotenv
from notte_core.common.config import LlmModel
from notte_sdk.client import NotteClient

_ = load_dotenv()


def test_agent_fallback():
    client = NotteClient()
    with client.Session(open_viewer=False) as session:
        _ = session.execute({"type": "goto", "url": "https://shop.notte.cc/"})
        _ = session.observe()
        # close modal if it appears
        _ = session.execute({"type": "click", "id": "B1"}, raise_on_failure=False)
        _ = session.observe()
        with client.AgentFallback(
            session,
            task="add the Cap product to cart",
            max_steps=3,
            reasoning_model=LlmModel.cerebras,
            use_vision=False,
        ) as agent_fallback:
            # Navigate to Cap product (L7 is typically the Cap link)
            _ = session.execute({"type": "click", "id": "L7"})
            # Use invalid ID to trigger agent fallback
            _ = session.execute({"type": "click", "id": "B999999"})

        agent = agent_fallback._agent  # pyright: ignore [reportPrivateUsage]
        assert agent is not None

        # ensure the agent was spawned and took action
        status = agent.status()
        assert len(status.steps) > 0, "Expected agent to have taken steps"
        # Find the first action step (agent_completion steps contain actions)
        action_step = None
        for step in status.steps:
            if step.get("type") == "agent_completion" and step.get("value", {}).get("action"):
                action_step = step
                break
        assert action_step is not None, f"Expected an action step, got steps: {[s['type'] for s in status.steps]}"
        action = action_step["value"]["action"]
        # Agent should click the add to cart button
        assert action["type"] == "click", f"Expected click, got {action}"

        # Verify the cart was updated by checking the page shows "added to cart"
        obs = session.observe()
        page_content = obs.space.description.lower()
        assert "added to cart" in page_content, f"Expected 'added to cart' in page content, got: {page_content[:500]}"


def test_agent_fallback_scrape_should_raise_error():
    client = NotteClient()
    with client.Session(open_viewer=False) as session:
        _ = session.execute({"type": "goto", "url": "https://shop.notte.cc/"})

        with pytest.raises(ValueError):
            with client.AgentFallback(session, task="add the Cap product to cart", max_steps=1):
                _ = session.scrape()


def test_agent_fallback_validator_with_page_navigation():
    """
    Test that the validator correctly handles page navigation scenarios.

    NOTE: This test uses the remote SDK client. The fix for this bug is in the local
    notte-agent package. Use test_agent_fallback_validator_with_page_navigation_local
    for testing the local fix.
    """
    pytest.skip("This test uses remote SDK - use the local test instead for validating the fix")
