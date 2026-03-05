"""
Test agent single step with various OpenRouter models.

This test verifies that the agent can successfully complete a single step
(observe + LLM completion) with different reasoning models via OpenRouter.
"""

import os

import notte_core.common.config as notte_config
import pytest
from dotenv import load_dotenv

import notte

# OpenRouter models to test - popular models from OpenRouter
# Format: <provider>/<model> - "openrouter/" prefix is auto-added
# Update this list as new models become available
OPENROUTER_MODELS = [
    "google/gemini-3-flash-preview",
    "google/gemini-2.5-flash",
    "anthropic/claude-opus-4.6",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-haiku-4.5",
    "openai/gpt-5.2",
    "openai/gpt-5-nano",
    "openai/gpt-4o-mini",
    "minimax/minimax-m2.5",
    "moonshotai/kimi-k2.5",
    "deepseek/deepseek-v3.2",
    "x-ai/grok-4.1-fast",
    "z-ai/glm-5",
    "qwen/qwen3.5-flash-02-23",
]


def to_openrouter_model(model: str) -> str:
    """Add openrouter/ prefix if not already present."""
    if model.startswith("openrouter/"):
        return model
    return f"openrouter/{model}"


def check_openrouter_available() -> bool:
    """Check if OpenRouter API key is available (read-only, no side-effects)."""
    load_dotenv()
    return os.getenv("OPENROUTER_API_KEY") is not None


@pytest.fixture(autouse=True, scope="module")
def enable_openrouter_for_module():
    """Enable OpenRouter mode for this test module with proper teardown."""
    original = os.environ.get("ENABLE_OPENROUTER")
    os.environ["ENABLE_OPENROUTER"] = "true"
    notte_config._enable_openrouter = None  # Reset cached value
    yield
    if original is None:
        os.environ.pop("ENABLE_OPENROUTER", None)
    else:
        os.environ["ENABLE_OPENROUTER"] = original
    notte_config._enable_openrouter = None  # Reset cached value


@pytest.fixture(scope="module")
def session():
    """Create a notte session for testing (module-scoped for efficiency)."""
    with notte.Session(headless=True) as s:
        # Navigate to a simple page first
        s.execute(type="goto", url="https://example.com")
        yield s


@pytest.mark.skipif(
    not check_openrouter_available(),
    reason="OPENROUTER_API_KEY not set",
)
@pytest.mark.parametrize("model", OPENROUTER_MODELS)
def test_single_agent_step_with_openrouter_model(session, model: str):
    """
    Test that a single agent step works with the given OpenRouter model.

    This test:
    1. Creates an agent with the specified reasoning model
    2. Runs the agent for just 1 step
    3. Verifies the agent successfully completed the step (no errors)
    """
    # Reset to known page state before each test to avoid cross-test pollution
    # (a previous agent may have navigated away from example.com)
    session.execute(type="goto", url="https://example.com")

    openrouter_model = to_openrouter_model(model)
    agent = notte.Agent(
        session=session,
        reasoning_model=openrouter_model,
        max_steps=1,  # Only run 1 step
        use_vision=False,  # Disable vision for models that don't support it
    )

    # Run the agent - it should complete 1 step and then stop
    # (either by completing the task or hitting max_steps)
    result = agent.run(task="Describe this page")

    # The agent should have run at least one step
    assert result is not None
    assert len(result.steps) >= 1, f"Agent did not complete any steps with model {model}"

    # The first step should have a valid action
    first_step = result.steps[0]
    assert first_step.action is not None, f"First step has no action with model {model}"
