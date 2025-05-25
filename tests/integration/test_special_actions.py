import pytest
from notte_browser.session import NotteSession, NotteSessionConfig
from notte_core.controller.actions import BrowserAction

from tests.mock.mock_service import MockLLMService


@pytest.fixture
def llm_service():
    return MockLLMService(mock_response="<data-extraction> # Hello World </data-extraction>")


def config():
    return NotteSessionConfig().headless()


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
async def test_goto_and_scrape(llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteSession(config(), llmserve=llm_service) as page:
        # Test S1: Go to URL
        obs = await page.execute(type="goto", value="https://github.com/")
        assert obs.clean_url == "github.com"

        # Test S2: Scrape data
        obs = await page.execute(type="scrape")
        assert obs.data is not None
        assert obs.data.markdown == "# Hello World"


@pytest.mark.asyncio
async def test_go_back_and_forward(llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteSession(config(), llmserve=llm_service) as page:
        # Test S4: Go to notte
        obs = await page.execute(type="goto", value="https://github.com/")
        assert obs.clean_url == "github.com"
        # Test S4: Go back
        obs = await page.execute(type="goto", value="https://google.com/")
        assert obs.clean_url == "google.com"
        obs = await page.execute(type="go_back")
        assert obs.clean_url == "github.com"

        # Test S5: Go forward
        obs = await page.execute(type="go_forward")
        assert obs.clean_url == "google.com"


@pytest.mark.asyncio
async def test_wait_and_complete(llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteSession(config(), llmserve=llm_service) as page:
        # Test S4: Go goto goole
        obs = await page.execute(type="goto", value="https://google.com/")
        assert obs.clean_url == "google.com"

        # Test S7: Wait
        _ = await page.execute(type="wait", value=1)

        _ = await page.goto("https://github.com/")


@pytest.mark.asyncio
async def test_special_action_validation(llm_service: MockLLMService):
    """Test validation of special action parameters"""
    async with NotteSession(config(), llmserve=llm_service) as page:
        _ = await page.goto("https://github.com/")
        # Test S1 requires URL parameter
        with pytest.raises(ValueError, match="validation error for GotoAction"):
            _ = await page.execute(type="goto")

        # Test S7 requires wait time parameter
        with pytest.raises(ValueError, match="validation error for WaitAction"):
            _ = await page.execute(type="wait")

        # Test invalid special action
        with pytest.raises(ValueError, match="Action with id 'X1' is invalid"):
            _ = await page.execute(action_id="X1")


@pytest.mark.asyncio
async def test_switch_tab(llm_service: MockLLMService):
    """Test the execution of the switch tab action"""
    async with NotteSession(config(), llmserve=llm_service) as page:
        obs = await page.goto("https://github.com/")
        assert len(obs.metadata.tabs) == 1
        assert obs.clean_url == "github.com"
        obs = await page.execute(
            type="goto_new_tab",
            value="https://google.com/",
        )
        assert len(obs.metadata.tabs) == 2
        assert obs.clean_url == "google.com"
        obs = await page.execute(type="switch_tab", value="0")
        assert obs.clean_url == "github.com"
        obs = await page.execute(type="switch_tab", value="1")
        assert obs.clean_url == "google.com"
