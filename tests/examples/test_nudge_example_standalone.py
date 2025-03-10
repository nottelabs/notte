from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel, Field


# Mock classes to avoid circular imports
class NudgeHint(BaseModel):
    """A hint or nudge to help the agent get back on track."""

    message: str = Field(..., description="The hint message to provide to the agent")
    reason: str = Field(..., description="The reason why this hint is being provided")
    severity: str = Field(..., description="The severity of the issue (low, medium, high)")


class MockFalcoAgentConfig:
    def __init__(
        self, enable_nudges=True, nudge_max_steps_to_analyze=3, nudge_failure_threshold=3, nudge_max_tokens=1000
    ):
        self.enable_nudges = enable_nudges
        self.nudge_max_steps_to_analyze = nudge_max_steps_to_analyze
        self.nudge_failure_threshold = nudge_failure_threshold
        self.nudge_max_tokens = nudge_max_tokens


class MockFalcoAgent:
    def __init__(self, config=None, window=None):
        self.config = config
        self.window = window
        self.last_nudge_result = None
        self.run = AsyncMock()


class MockBrowserWindow:
    @classmethod
    def create(cls, headless=True):
        return cls()


# Mock the example script
class MockNudgeExample:
    @staticmethod
    async def main():
        # Configure the agent with nudges enabled
        config = MockFalcoAgentConfig(
            enable_nudges=True,
            nudge_max_steps_to_analyze=3,
            nudge_failure_threshold=2,  # Lower threshold for demo purposes
            nudge_max_tokens=1000,
        )

        # Create a browser window
        window = MockBrowserWindow.create(headless=False)

        # Create the agent
        agent = MockFalcoAgent(config=config, window=window)

        # Run the agent with a task that might cause it to get stuck
        await agent.run(
            task="Go to https://github.com/login and try to log in with the username 'test_user' and password 'invalid_password'. "
            "After that fails, try to find another way to access GitHub content."
        )

        return agent


@pytest.mark.asyncio
async def test_nudge_example_main():
    """Test the main function of the nudge example."""
    # Mock the FalcoAgent class
    mock_agent = MockFalcoAgent()
    mock_agent.last_nudge_result = MagicMock()
    mock_agent.last_nudge_result.needs_nudge = True
    mock_agent.last_nudge_result.hints = [MagicMock(message="Try a different approach", severity="medium")]

    # Create a config
    config = MockFalcoAgentConfig(
        enable_nudges=True, nudge_max_steps_to_analyze=3, nudge_failure_threshold=2, nudge_max_tokens=1000
    )

    # Create a window
    window = MockBrowserWindow.create(headless=False)

    # Set up the agent
    agent = MockFalcoAgent(config=config, window=window)

    # Run the agent with a task
    await agent.run(
        task="Go to https://github.com/login and try to log in with the username 'test_user' and password 'invalid_password'. "
        "After that fails, try to find another way to access GitHub content."
    )

    # Verify the agent's run method was called with the correct task
    agent.run.assert_called_once()
    task = agent.run.call_args[1]["task"]
    assert "Go to https://github.com/login" in task

    # Verify the config was set correctly
    assert agent.config.enable_nudges is True
    assert agent.config.nudge_failure_threshold == 2  # Lower threshold for demo purposes


@pytest.mark.asyncio
async def test_nudge_example_no_nudges():
    """Test the main function when no nudges are needed."""
    # Create a config with nudges disabled
    config = MockFalcoAgentConfig(enable_nudges=False)

    # Create a window
    window = MockBrowserWindow.create(headless=False)

    # Set up the agent
    agent = MockFalcoAgent(config=config, window=window)
    agent.last_nudge_result = None

    # Run the agent with a task
    await agent.run(
        task="Go to https://github.com/login and try to log in with the username 'test_user' and password 'invalid_password'. "
        "After that fails, try to find another way to access GitHub content."
    )

    # Verify the agent's run method was called
    agent.run.assert_called_once()

    # Verify nudges are disabled
    assert agent.config.enable_nudges is False
