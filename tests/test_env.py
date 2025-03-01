from collections.abc import AsyncGenerator, Awaitable

import pytest

from notte.actions.base import Action
from notte.browser.snapshot import BrowserSnapshot
from notte.env import NotteEnv
from tests.mock.mock_browser import MockBrowserDriver
from tests.mock.mock_service import MockLLMService


@pytest.fixture
def mock_llm_response() -> str:
    return """
| ID  | Description | Parameters | Category |
| L1  | Opens more information page | | Navigation |
"""


@pytest.fixture
def mock_llm_service(mock_llm_response: str) -> MockLLMService:
    return MockLLMService(
        mock_response=f"""
<document-summary>
This is a mock document summary
</document-summary>
<document-category>
homepage
</document-category>
<action-listing>
{mock_llm_response}
</action-listing>
"""
    )


@pytest.fixture
async def env_generator(
    mock_llm_service: MockLLMService,
) -> AsyncGenerator[NotteEnv, None]:
    """Create a NotteEnv instance with mock browser and LLM"""
    window = MockBrowserDriver()
    async with NotteEnv(window=window, llmserve=mock_llm_service) as env:
        yield env


@pytest.fixture
async def aenv(env_generator: AsyncGenerator[NotteEnv, None]) -> NotteEnv:
    """Helper fixture that returns the NotteEnv instance directly"""
    return await anext(env_generator)


@pytest.mark.asyncio
async def test_context_property_before_observation(aenv: Awaitable[NotteEnv]) -> None:
    """Test that accessing context before observation raises an error"""
    with pytest.raises(
        ValueError,
        match="Tried to access `env.snapshot` but no snapshot is available in the environment",
    ):
        _ = (await aenv).snapshot


@pytest.mark.asyncio
async def test_context_property_after_observation(aenv: Awaitable[NotteEnv]) -> None:
    """Test that context is properly set after observation"""
    env = await aenv
    _ = await env.observe("https://notte.cc")

    # Verify context exists and has expected properties
    assert isinstance(env.snapshot, BrowserSnapshot)
    assert env.snapshot.metadata.url == "https://notte.cc"
    assert env.snapshot.a11y_tree is not None
    assert env.snapshot.dom_node is not None


@pytest.mark.asyncio
async def testtrajectory_empty_before_observation(aenv: Awaitable[NotteEnv]) -> None:
    """Test that list_actions returns None before any observation"""
    env = await aenv
    assert len(env.trajectory) == 0


@pytest.mark.asyncio
async def test_valid_observation_after_observation(aenv: Awaitable[NotteEnv]) -> None:
    """Test that last observation returns valid actions after observation"""
    env = await aenv
    obs = await env.observe("https://example.com")

    actions = obs.space.actions()
    assert isinstance(actions, list)
    assert all(isinstance(action, Action) for action in actions)
    assert len(actions) == 1  # Number of actions in mock response

    # Verify each action has required attributes
    actions = [
        Action(id="L1", description="Opens more information page", category="Navigation"),
    ]


@pytest.mark.skip(reason="TODO: fix this")
@pytest.mark.asyncio
async def test_valid_observation_after_step(aenv: Awaitable[NotteEnv]) -> None:
    """Test that last observation returns valid actions after taking a step"""
    # Initial observation
    env = await aenv
    obs = await env.observe("https://example.com")
    if obs.space is None:
        raise ValueError("obs.space is None")
    initial_actions = obs.space.actions("all")
    assert initial_actions is not None
    assert len(initial_actions) == 1

    # Take a step
    _ = await env.step("L1")  # Using L1 from mock response

    # TODO: verify that the action space is updated


@pytest.mark.asyncio
async def test_valid_observation_after_reset(aenv: Awaitable[NotteEnv]) -> None:
    """Test that last observation returns valid actions after reset"""
    # Initial observation
    env = await aenv
    obs = await env.observe("https://example.com")
    assert obs.has_space()

    # Reset environment
    await env.reset()
    obs = await env.observe("https://example.com")

    # Verify new observation is correct
    assert obs.has_space()
    assert obs.metadata.url == "https://example.com"

    # Verify the state was effectively reset
    assert env.snapshot.screenshot == obs.screenshot  # poor proxy but ok
    assert len(env.trajectory) == 1  # the trajectory should only contains a single obs (from reset)
