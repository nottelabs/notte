import pytest
from notte_browser.session import NotteSession
from notte_core.actions.percieved import PerceivedAction
from notte_core.browser.snapshot import BrowserSnapshot

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


@pytest.mark.asyncio
async def test_context_property_before_observation(mock_llm_service: MockLLMService) -> None:
    """Test that accessing context before observation raises an error"""
    with pytest.raises(
        ValueError,
        match="Tried to access `session.snapshot` but no snapshot is available in the session",
    ):
        async with NotteSession(window=MockBrowserDriver(), llmserve=mock_llm_service) as page:
            _ = page.snapshot


@pytest.mark.asyncio
async def test_context_property_after_observation(mock_llm_service: MockLLMService) -> None:
    """Test that context is properly set after observation"""
    async with NotteSession(window=MockBrowserDriver(), llmserve=mock_llm_service) as page:
        _ = await page.observe("https://notte.cc")

    # Verify context exists and has expected properties
    assert isinstance(page.snapshot, BrowserSnapshot)
    assert page.snapshot.metadata.url == "https://notte.cc"
    assert page.snapshot.a11y_tree is not None
    assert page.snapshot.dom_node is not None


@pytest.mark.asyncio
async def test_trajectory_empty_before_observation(mock_llm_service: MockLLMService) -> None:
    """Test that list_actions returns None before any observation"""
    async with NotteSession(window=MockBrowserDriver(), llmserve=mock_llm_service) as page:
        assert len(page.trajectory) == 0


@pytest.mark.asyncio
async def test_valid_observation_after_observation(mock_llm_service: MockLLMService) -> None:
    """Test that last observation returns valid actions after observation"""
    async with NotteSession(window=MockBrowserDriver(), llmserve=mock_llm_service) as page:
        obs = await page.observe("https://example.com")

    assert obs.space is not None
    actions = obs.space.actions
    assert isinstance(actions, list)
    assert all(isinstance(action, PerceivedAction) for action in actions)
    assert len(actions) == 1  # Number of actions in mock response

    # Verify each action has required attributes
    actions = [
        PerceivedAction(id="L1", description="Opens more information page", category="Navigation"),
    ]


@pytest.mark.skip(reason="TODO: fix this")
@pytest.mark.asyncio
async def test_valid_observation_after_step(mock_llm_service: MockLLMService) -> None:
    """Test that last observation returns valid actions after taking a step"""
    # Initial observation
    async with NotteSession(window=MockBrowserDriver(), llmserve=mock_llm_service) as page:
        obs = await page.observe("https://example.com")
        if obs.space is None:
            raise ValueError("obs.space is None")
        initial_actions = obs.space.actions
        assert initial_actions is not None
        assert len(initial_actions) == 1

        # Take a step
        _ = await page.step("L1")  # Using L1 from mock response

        # TODO: verify that the action space is updated


@pytest.mark.asyncio
async def test_valid_observation_after_reset(mock_llm_service: MockLLMService) -> None:
    """Test that last observation returns valid actions after reset"""
    # Initial observation
    async with NotteSession(window=MockBrowserDriver(), llmserve=mock_llm_service) as page:
        obs = await page.observe("https://example.com")

        # Reset environment
        await page.reset()
        obs = await page.observe("https://example.com")

        # Verify new observation is correct
        assert len(obs.space.actions) > 0
        assert "https://example.com" in obs.metadata.url

        # Verify the state was effectively reset
        assert page.snapshot.screenshot == obs.screenshot  # poor proxy but ok
        assert len(page.trajectory) == 1  # the trajectory should only contains a single obs (from reset)
