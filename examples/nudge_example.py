#!/usr/bin/env python3
"""
Example demonstrating the agent nudge component.

This example shows how the nudge component helps agents recover from errors
or when they get stuck in a loop.
"""

import asyncio

from loguru import logger

from notte.agents import FalcoAgent, FalcoAgentConfig
from notte.browser.window import BrowserWindow


async def main() -> None:
    """Run the example."""
    # Configure the agent with nudges enabled
    config = FalcoAgentConfig(
        enable_nudges=True,
        nudge_max_steps_to_analyze=3,
        nudge_failure_threshold=2,  # Lower threshold for demo purposes
        nudge_max_tokens=1000,
    )

    # Create a browser window
    # Using type: ignore to suppress the type checker warning about BrowserWindow.create
    window = BrowserWindow.create(headless=False)  # type: ignore

    # Create the agent with explicit type annotation for window parameter
    agent = FalcoAgent(
        config=config,
        window=window,  # type: ignore
    )

    # Run the agent with a task that might cause it to get stuck
    # For example, trying to log in to a site with invalid credentials
    task = (
        "Go to https://github.com/login and try to log in with the username 'test_user' and password 'invalid_password'. "
        "After that fails, try to find another way to access GitHub content."
    )
    response = await agent.run(task=task)

    # Print the agent's response
    logger.info(f"Agent response: {response}")

    # Check if nudges were provided
    if agent.last_nudge_result and agent.last_nudge_result.needs_nudge:
        logger.info("Nudges were provided to the agent:")
        for hint in agent.last_nudge_result.hints:
            logger.info(f"- {hint.message} (Severity: {hint.severity})")
    else:
        logger.info("No nudges were needed during this run.")


if __name__ == "__main__":
    asyncio.run(main())
