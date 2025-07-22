import pytest
from notte_browser.errors import ScrollActionFailedError
from notte_browser.session import NotteSession
from notte_core.actions import BrowserAction, ClickAction
from notte_core.browser.observation import ExecutionResult
from notte_core.common.config import BrowserType, PerceptionType
from notte_core.errors.base import ErrorConfig

from tests.mock.mock_service import MockLLMService
from tests.mock.mock_service import patch_llm_service as _patch_llm_service

patch_llm_service = _patch_llm_service


@pytest.fixture
def mock_llm_service():
    return MockLLMService(mock_response="<data-extraction> # Hello World </data-extraction>")


def test_browser_actions_list():
    """Test that all special actions are properly defined"""
    browser_actions = BrowserAction.list()

    # Test we have all 8 special actions
    assert len(browser_actions) == len(BrowserAction.BROWSER_ACTION_REGISTRY)

    # Test each special action ID exists
    action_ids = set([action.type for action in browser_actions])
    expected_ids = set(BrowserAction.BROWSER_ACTION_REGISTRY.keys())
    assert action_ids == expected_ids

    # Test special action detection
    for action_id in expected_ids:
        assert BrowserAction.is_browser_action(action_id)

    # Test non-special action detection
    assert not BrowserAction.is_browser_action("B1")
    assert not BrowserAction.is_browser_action("I1")
    assert not BrowserAction.is_browser_action("L1")


@pytest.mark.asyncio
async def test_goto_and_scrape():
    """Test the execution of various special actions"""
    async with NotteSession(headless=True) as page:
        # Test S1: Go to URL
        _ = await page.aexecute(type="goto", value="https://example.com/")
        obs = await page.aobserve(perception_type=PerceptionType.FAST)
        assert obs.clean_url == "example.com"

        example_com_str = "\n\n\n\n\n\nThis domain is for use in illustrative examples in documents. You may use this domain in literature without prior coordination or asking for permission.\n\nMore information...\n\n\n\n"

        # Test S2: Scrape data
        data = await page.ascrape()
        assert data.markdown == example_com_str, f"Expected typical example.com str, got {data.markdown}"


@pytest.mark.asyncio
async def test_go_back_and_forward(patch_llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteSession(headless=True) as page:
        # Test S4: Go to notte
        _ = await page.aexecute(type="goto", value="https://github.com/")
        obs = await page.aobserve(perception_type=PerceptionType.FAST)
        assert obs.clean_url == "github.com"
        # Test S4: Go back
        _ = await page.aexecute(type="goto", value="https://google.com/")
        obs = await page.aobserve(perception_type=PerceptionType.FAST)
        assert "google.com" in obs.clean_url
        _ = await page.aexecute(type="go_back")
        obs = await page.aobserve(perception_type=PerceptionType.FAST)
        assert obs.clean_url == "github.com"

        # Test S5: Go forward
        _ = await page.aexecute(type="go_forward")
        obs = await page.aobserve(perception_type=PerceptionType.FAST)
        assert "google.com" in obs.clean_url


@pytest.mark.asyncio
async def test_wait_and_complete(patch_llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteSession(headless=True) as page:
        # Test S4: Go goto goole
        _ = await page.aexecute(type="goto", value="https://google.com/")
        obs = await page.aobserve(perception_type=PerceptionType.FAST)

        assert "google.com" in obs.clean_url

        # Test S7: Wait
        _ = await page.aexecute(type="wait", value=1)

        _ = await page.aobserve(perception_type=PerceptionType.FAST)


@pytest.mark.asyncio
async def test_special_action_validation(patch_llm_service: MockLLMService):
    """Test validation of special action parameters"""
    async with NotteSession(headless=True) as page:
        _ = await page.aexecute(type="goto", value="https://github.com/")
        _ = await page.aobserve(perception_type=PerceptionType.FAST)
        # Test S1 requires URL parameter
        with pytest.raises(ValueError, match="validation error for GotoAction"):
            _ = await page.aexecute(type="goto")

        # Test S7 requires wait time parameter
        with pytest.raises(ValueError, match="validation error for WaitAction"):
            _ = await page.aexecute(type="wait")

        def check_failure(result: ExecutionResult) -> None:
            assert not result.success
            assert isinstance(result.exception, ValueError)
            assert "Action with id 'X1' is invalid" in result.message

        # Test invalid special action, multi combinations
        result = await page.aexecute(type="click", action_id="X1")
        check_failure(result)

        result = await page.aexecute(ClickAction(id="X1"))
        check_failure(result)

        result = page.execute(type="click", action_id="X1")
        check_failure(result)

        result = page.execute(ClickAction(id="X1"))
        check_failure(result)


async def test_switch_tab(patch_llm_service: MockLLMService):
    """Test the execution of the switch tab action"""
    with NotteSession(headless=True) as page:
        _ = await page.aexecute(type="goto", value="https://github.com/")
        obs = await page.aobserve(perception_type=PerceptionType.FAST)
        assert len(obs.metadata.tabs) == 1
        assert obs.clean_url == "github.com"

        _ = await page.aexecute(
            type="goto_new_tab",
            value="https://google.com/",
        )
        obs = await page.aobserve(perception_type=PerceptionType.FAST)
        assert len(obs.metadata.tabs) == 2
        assert "google.com" in obs.clean_url

        _ = page.execute(type="switch_tab", value="0")
        obs = await page.aobserve()
        assert obs.clean_url == "github.com"

        _ = page.execute(type="switch_tab", value="1")
        obs = await page.aobserve()
        assert "google.com" in obs.clean_url


@pytest.mark.asyncio
async def test_scroll_on_non_scrollable_page_should_fail():
    assert ErrorConfig.get_message_mode().value == "developer"
    async with NotteSession() as session:
        assert ErrorConfig.get_message_mode().value == "developer"
        _ = await session.aexecute(type="goto", value="https://www.google.com/")
        _ = await session.aobserve(perception_type=PerceptionType.FAST)
        assert ErrorConfig.get_message_mode().value == "developer"
        res = await session.aexecute(type="scroll_down")
        assert not res.success
        assert isinstance(res.exception, ScrollActionFailedError)
        assert res.message == ScrollActionFailedError().agent_message


@pytest.mark.asyncio
async def test_scroll_on_scrollable_page_should_succeed():
    async with NotteSession(browser_type=BrowserType.CHROME) as session:
        res = await session.aexecute(type="goto", value="https://duckduckgo.com/")
        assert res.success
        obs = await session.aobserve(perception_type=PerceptionType.FAST)
        res = await session.aexecute(type="scroll_down")
        obs2 = await session.aobserve(perception_type=PerceptionType.FAST)
        assert res.success, f"Viewport obs2: {obs2.metadata.viewport}"
        assert obs.metadata.viewport.scroll_x == obs2.metadata.viewport.scroll_x
        assert obs.metadata.viewport.scroll_y != obs2.metadata.viewport.scroll_y
        res = await session.aexecute(type="scroll_up")
        assert res.success
        obs3 = await session.aobserve(perception_type=PerceptionType.FAST)
        assert obs3.metadata.viewport.scroll_x == obs2.metadata.viewport.scroll_x
        assert obs3.metadata.viewport.scroll_y != obs2.metadata.viewport.scroll_y
        assert obs3.metadata.viewport.scroll_y == obs.metadata.viewport.scroll_y
