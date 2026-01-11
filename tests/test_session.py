import notte_core
import pytest
from notte_browser.captcha import CaptchaHandler
from notte_browser.errors import CaptchaSolverNotAvailableError, NoSnapshotObservedError, ScrollActionFailedError
from notte_browser.session import NotteSession
from notte_core.actions import (
    ClickAction,
    GotoAction,
    GotoNewTabAction,
    InteractionAction,
    ScrollDownAction,
    SwitchTabAction,
    WaitAction,
)
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.errors.actions import InvalidActionError
from notte_llm.service import LLMService

from tests.mock.mock_browser import MockBrowserDriver
from tests.mock.mock_service import MockLLMService
from tests.mock.mock_service import patch_llm_service as _patch_llm_service

patch_llm_service = _patch_llm_service

notte_core.set_error_mode("developer")


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
async def test_context_property_before_observation(patch_llm_service: MockLLMService) -> None:
    """Test that accessing context before observation raises an error"""
    with pytest.raises(
        NoSnapshotObservedError,
    ):
        async with NotteSession(window=MockBrowserDriver()) as page:
            _ = page.snapshot


@pytest.mark.asyncio
async def test_context_property_after_observation(patch_llm_service: MockLLMService) -> None:
    """Test that context is properly set after observation"""
    driver = MockBrowserDriver()
    async with NotteSession(window=driver) as page:
        _ = await page.aexecute(GotoAction(url="https://notte.cc"))
        _ = await page.aobserve()

    # Verify context exists and has expected properties
    assert isinstance(page.snapshot, BrowserSnapshot)
    assert page.snapshot.metadata.url == "https://notte.cc"
    assert page.snapshot.a11y_tree is None
    assert page.snapshot.dom_node is not None


@pytest.mark.asyncio
async def test_trajectory_empty_before_observation(patch_llm_service: MockLLMService) -> None:
    """Test that list_actions returns None before any observation"""
    async with NotteSession(window=MockBrowserDriver()) as page:
        assert len(page.trajectory) == 0


@pytest.mark.asyncio
async def test_valid_observation_after_observation(patch_llm_service: MockLLMService) -> None:
    """Test that last observation returns valid actions after observation"""
    async with NotteSession(window=MockBrowserDriver()) as page:
        _ = await page.aexecute(GotoAction(url="https://www.example.com"))
        obs = await page.aobserve()

    assert obs.space is not None
    actions = obs.space.interaction_actions
    assert isinstance(actions, list)
    assert all(isinstance(action, InteractionAction) for action in actions)
    assert len(actions) == 1  # Number of actions in mock response

    # Verify each action has required attributes
    actions = [
        ClickAction(id="L1", description="Opens more information page", category="Navigation"),
    ]


@pytest.mark.skip(reason="TODO: fix this")
@pytest.mark.asyncio
async def test_valid_observation_after_step(patch_llm_service: MockLLMService) -> None:
    """Test that last observation returns valid actions after taking a step"""
    # Initial observation
    async with NotteSession(window=MockBrowserDriver()) as page:
        _ = await page.aexecute(GotoAction(url="https://www.example.com"))
        obs = await page.aobserve()
        initial_actions = obs.space.interaction_actions
        assert initial_actions is not None
        assert len(initial_actions) == 1

        # Take a step
        _ = await page.aexecute(type="click", id="L1")  # Using L1 from mock response

        # TODO: verify that the action space is updated


@pytest.mark.asyncio
async def test_llm_service_from_config(patch_llm_service: MockLLMService, mock_llm_response) -> None:
    """Test that LLMService.from_config returns the mock service"""
    service = LLMService.from_config()
    assert isinstance(service, MockLLMService)
    assert service.mock_response == patch_llm_service.mock_response
    assert mock_llm_response in (await service.completion(prompt_id="test", variables={})).choices[0].message.content


@pytest.mark.asyncio
async def test_step_should_fail_without_observation() -> None:
    """Test that step should fail without observation"""
    async with NotteSession() as page:
        with pytest.raises(NoSnapshotObservedError):
            _ = await page.aexecute(ClickAction(id="L1"))


@pytest.mark.asyncio
async def test_step_should_succeed_after_observation() -> None:
    """Test that step should fail without observation"""
    async with NotteSession() as page:
        _ = await page.aexecute(type="goto", value="https://www.example.com")
        _ = await page.aobserve(perception_type="fast")
        _ = await page.aexecute(ClickAction(id="L1"))


@pytest.mark.asyncio
async def test_browser_action_step_should_succeed_without_observation() -> None:
    """Test that step should fail without observation"""
    async with NotteSession() as page:
        _ = await page.aexecute(GotoAction(url="https://www.example.com"))
        _ = await page.aexecute(GotoNewTabAction(url="https://www.example.com"))
        _ = await page.aexecute(SwitchTabAction(tab_index=0))
        _ = await page.aexecute(WaitAction(time_ms=1000))
        with pytest.raises(ScrollActionFailedError):
            # scroll should fail because the page is not scrollable
            _ = await page.aexecute(ScrollDownAction())


@pytest.mark.asyncio
@pytest.mark.parametrize("action_id", ["INVALID_ACTION_ID", "B999", "X999"])
async def test_step_with_invalid_action_id_returns_failed_result(action_id: str):
    """Test that stepping with an invalid action ID returns a failed StepResult."""

    async with NotteSession() as session:
        # First observe a page to get a snapshot
        _ = await session.aexecute(type="goto", value="https://www.example.com")
        _ = await session.aobserve(perception_type="fast")
        # Try to step with an invalid action ID that doesn't exist on the page
        step_response = await session.aexecute(type="click", id=action_id, raise_on_failure=False)

        # Verify that the step failed
        assert not step_response.success
        assert "invalid" in step_response.message.lower() or "not found" in step_response.message.lower()
        assert step_response.exception is not None


@pytest.mark.asyncio
async def test_step_with_empty_action_id_should_fail_validation_pydantic():
    """Test that stepping with an invalid action ID returns a failed StepResult."""

    async with NotteSession() as session:
        # First observe a page to get a snapshot
        _ = await session.aexecute(type="goto", value="https://www.example.com")
        _ = await session.aobserve(perception_type="fast")
        # Try to step with an invalid action ID that doesn't exist on the page
        res = await session.aexecute(type="click", id="action_id", raise_on_failure=False)
        assert not res.success, f"Expected failure, got {res}"
        assert res.exception is not None, f"Expected exception, got {res}"
        assert isinstance(res.exception, InvalidActionError)


def test_captcha_solver_not_available_error():
    with pytest.raises(CaptchaSolverNotAvailableError):
        _ = NotteSession(solve_captchas=True, browser_type="firefox")

    CaptchaHandler.is_available = True
    _ = NotteSession(solve_captchas=True, browser_type="firefox")
    CaptchaHandler.is_available = False


# ============================================
# Timeout parameter tests
# ============================================


@pytest.mark.asyncio
async def test_execute_with_default_timeout() -> None:
    """Test that execute works with default timeout from config."""
    from notte_core.common.config import config

    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url="https://www.google.com")
        _ = await session.aobserve(perception_type="fast")
        # Execute with default timeout (should use config.timeout_action_ms = 5000ms)
        # Try to click on first button (may fail if not found, but timeout param should work)
        result = await session.aexecute(type="click", id="B1", raise_on_failure=False)
        assert result is not None
        assert config.timeout_action_ms == 5000  # Verify default


@pytest.mark.asyncio
async def test_execute_with_custom_timeout() -> None:
    """Test that execute accepts custom timeout parameter."""
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url="https://www.google.com")
        _ = await session.aobserve(perception_type="fast")
        # Execute with custom timeout (10 seconds)
        result = await session.aexecute(type="click", id="B1", timeout=10000, raise_on_failure=False)
        assert result is not None
