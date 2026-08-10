"""
Test agent single step with various OrcaRouter models.

This test verifies that the agent can successfully complete a single step
(observe + LLM completion) with different reasoning models via OrcaRouter.
"""

import os

import notte_core.common.config as notte_config
import pytest
from dotenv import load_dotenv

import notte

# OrcaRouter models to test - models served by the OrcaRouter catalog
# Format: <provider>/<model> - full namespaced ids, no extra prefix needed
# Update this list as new models become available
ORCAROUTER_MODELS = [
    "google/gemini-3.5-flash",
    "google/gemini-2.5-flash",
    "anthropic/claude-opus-4.6",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-haiku-4.5",
    "openai/gpt-5.2",
    "openai/gpt-5-nano",
    "openai/gpt-4o-mini",
    "minimax/minimax-m2.5",
    "kimi/kimi-k2.5",
    "deepseek/deepseek-v4-flash",
    "grok/grok-4.3",
    "z-ai/glm-5",
    "qwen/qwen3.5-flash",
]


def to_orcarouter_model(model: str) -> str:
    """Return the full OrcaRouter model id (ids are already namespaced)."""
    return model


def check_orcarouter_available() -> bool:
    """Check if OrcaRouter API key is available.

    Note: Relies on load_dotenv() having been called at module import time.
    """
    return os.getenv("ORCAROUTER_API_KEY") is not None


# Load .env at module import time (before pytest collection evaluates skipif)
load_dotenv()


@pytest.fixture(autouse=True, scope="module")
def enable_orcarouter_for_module():
    """Enable OrcaRouter mode for this test module with proper teardown."""
    original = os.environ.get("ENABLE_ORCAROUTER")
    os.environ["ENABLE_ORCAROUTER"] = "true"
    notte_config._enable_orcarouter = None  # Reset cached value
    yield
    if original is None:
        os.environ.pop("ENABLE_ORCAROUTER", None)
    else:
        os.environ["ENABLE_ORCAROUTER"] = original
    notte_config._enable_orcarouter = None  # Reset cached value


@pytest.fixture(scope="module")
def session():
    """Create a notte session for testing (module-scoped for efficiency)."""
    with notte.Session(headless=True) as s:
        # Navigate to a simple page first
        s.execute(type="goto", url="https://example.com")
        yield s


@pytest.mark.skipif(
    not check_orcarouter_available(),
    reason="ORCAROUTER_API_KEY not set",
)
@pytest.mark.parametrize("model", ORCAROUTER_MODELS)
def test_single_agent_step_with_orcarouter_model(session, model: str):
    """
    Test that a single agent step works with the given OrcaRouter model.

    This test:
    1. Creates an agent with the specified reasoning model
    2. Runs the agent for just 1 step
    3. Verifies the agent successfully completed the step (no errors)
    """
    # Reset to known page state before each test to avoid cross-test pollution
    # (a previous agent may have navigated away from example.com)
    session.execute(type="goto", url="https://example.com")

    agent = notte.Agent(
        session=session,
        reasoning_model=to_orcarouter_model(model),
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
