import pytest
from notte_browser.session import NotteSession
from notte_core.actions import BrowserAction

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
async def test_goto_and_scrape(patch_llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteSession(headless=True, enable_perception=False) as page:
        # Test S1: Go to URL
        _ = await page.astep(type="goto", value="https://github.com/")
        obs = await page.aobserve()
        assert obs.clean_url == "github.com"

        # Test S2: Scrape data
        data = await page.ascrape(use_llm=True)
        assert data.markdown == "# Hello World", f"Expected '# Hello World', got {data.markdown}"


@pytest.mark.asyncio
async def test_go_back_and_forward(patch_llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteSession(headless=True, enable_perception=False) as page:
        # Test S4: Go to notte
        _ = await page.astep(type="goto", value="https://github.com/")
        obs = await page.aobserve()
        assert obs.clean_url == "github.com"
        # Test S4: Go back
        _ = await page.astep(type="goto", value="https://google.com/")
        obs = await page.aobserve()
        assert "google.com" in obs.clean_url
        _ = await page.astep(type="go_back")
        obs = await page.aobserve()
        assert obs.clean_url == "github.com"

        # Test S5: Go forward
        _ = await page.astep(type="go_forward")
        obs = await page.aobserve()
        assert "google.com" in obs.clean_url


@pytest.mark.asyncio
async def test_wait_and_complete(patch_llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteSession(headless=True, enable_perception=False) as page:
        # Test S4: Go goto goole
        _ = await page.astep(type="goto", value="https://google.com/")
        obs = await page.aobserve()
        assert "google.com" in obs.clean_url

        # Test S7: Wait
        _ = await page.astep(type="wait", value=1)

        _ = await page.aobserve("https://github.com/")


@pytest.mark.asyncio
async def test_special_action_validation(patch_llm_service: MockLLMService):
    """Test validation of special action parameters"""
    async with NotteSession(headless=True, enable_perception=False) as page:
        _ = await page.aobserve("https://github.com/")
        # Test S1 requires URL parameter
        with pytest.raises(ValueError, match="validation error for StepRequest"):
            _ = await page.astep(type="goto")

        # Test S7 requires wait time parameter
        with pytest.raises(ValueError, match="validation error for StepRequest"):
            _ = await page.astep(type="wait")

        # Test invalid special action
        result = await page.astep(type="click", action_id="X1")
        assert not result.success
        assert isinstance(result.exception, ValueError)
        assert "Action with id 'X1' is invalid" in result.message


async def test_switch_tab(patch_llm_service: MockLLMService):
    """Test the execution of the switch tab action"""
    with NotteSession(headless=True) as page:
        obs = page.observe("https://github.com/")
        assert len(obs.metadata.tabs) == 1
        assert obs.clean_url == "github.com"

        _ = await page.astep(
            type="goto_new_tab",
            value="https://google.com/",
        )
        obs = await page.aobserve()
        assert len(obs.metadata.tabs) == 2
        assert "google.com" in obs.clean_url

        _ = page.step(type="switch_tab", value="0")
        obs = await page.aobserve()
        assert obs.clean_url == "github.com"

        _ = page.step(type="switch_tab", value="1")
        obs = await page.aobserve()
        assert "google.com" in obs.clean_url
