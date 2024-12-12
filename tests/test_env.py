from collections.abc import AsyncGenerator, Awaitable

import pytest

from notte.actions.base import Action
from notte.browser.context import Context
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
<action-listing>
{mock_llm_response}
</action-listing>
"""
    )


@pytest.fixture
async def env_generator(mock_llm_service: MockLLMService) -> AsyncGenerator[NotteEnv, None]:
    """Create a NotteEnv instance with mock browser and LLM"""
    browser = MockBrowserDriver()
    async with NotteEnv(browser=browser, llmserve=mock_llm_service) as env:
        yield env


@pytest.fixture
async def aenv(env_generator: AsyncGenerator[NotteEnv, None]) -> NotteEnv:
    """Helper fixture that returns the NotteEnv instance directly"""
    return await anext(env_generator)


@pytest.mark.asyncio
async def test_context_property_before_observation(aenv: Awaitable[NotteEnv]) -> None:
    """Test that accessing context before observation raises an error"""
    with pytest.raises(ValueError, match="Need to observe first to get a context."):
        _ = (await aenv).context


@pytest.mark.asyncio
async def test_context_property_after_observation(aenv: Awaitable[NotteEnv]) -> None:
    """Test that context is properly set after observation"""
    env = await aenv
    _ = await env.observe("https://example.com")

    # Verify context exists and has expected properties
    assert isinstance(env.context, Context)
    assert env.context.snapshot.url == "https://example.com"
    assert env.context.snapshot.a11y_tree is not None
    assert env.context.node is not None


@pytest.mark.asyncio
async def test_list_actions_before_observation(aenv: Awaitable[NotteEnv]) -> None:
    """Test that list_actions returns None before any observation"""
    env = await aenv
    assert env.list_actions is None


@pytest.mark.asyncio
async def test_list_actions_after_observation(aenv: Awaitable[NotteEnv]) -> None:
    """Test that list_actions returns valid actions after observation"""
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


@pytest.mark.asyncio
async def test_list_actions_invalidation_after_navigation(aenv: Awaitable[NotteEnv]) -> None:
    """Test that list_actions is invalidated after navigating to a new page"""
    # Initial observation
    env = await aenv
    obs = await env.observe("https://example.com")
    assert env.list_actions is not None
    assert obs.space is not None

    # Navigate to new page
    obs = await env.goto("https://another-example.com")
    assert env.list_actions is None
    assert obs.space is None


@pytest.mark.asyncio
async def test_list_actions_after_step(aenv: Awaitable[NotteEnv]) -> None:
    """Test that list_actions is updated after taking a step"""
    # Initial observation
    env = await aenv
    _ = await env.observe("https://example.com")
    initial_actions = env.list_actions
    assert initial_actions is not None
    assert len(initial_actions) == 1

    # Take a step
    _ = await env.step("L1")  # Using L1 from mock response

    # TODO: verify that the action space is updated


@pytest.mark.asyncio
async def test_list_actions_after_reset(aenv: Awaitable[NotteEnv]) -> None:
    """Test that list_actions is properly reset"""
    # Initial observation
    env = await aenv
    _ = await env.observe("https://example.com")
    assert env.list_actions is not None

    # Reset environment
    _ = await env.reset("https://example.com")

    # Verify new action list
    assert env.list_actions is not None
    assert env.context.snapshot.url == "https://example.com"
    assert isinstance(env.list_actions, list)
    assert all(isinstance(action, Action) for action in env.list_actions)


@pytest.mark.asyncio
async def test_context_and_actions_consistency(aenv: Awaitable[NotteEnv]) -> None:
    """Test that context and list_actions are consistent with each other"""
    env = await aenv
    _ = await env.observe("https://example.com")

    # Verify context and actions exist
    assert isinstance(env.context, Context)
    assert isinstance(env.list_actions, list)

    # Get all node IDs from context
    node_ids = {node.id for node in env.context.interaction_nodes()}

    # Verify each action ID exists in context nodes
    for action in env.list_actions:
        assert action.id in node_ids
