import pytest

from notte.actions.base import SpecialAction, SpecialActionId
from notte.env import NotteEnv
from tests.mock.mock_service import MockLLMService


@pytest.fixture
def llm_service():
    return MockLLMService(mock_response="<data-extraction> # Hello World </data-extraction>")


def test_special_actions_list():
    """Test that all special actions are properly defined"""
    special_actions = SpecialAction.list()

    # Test we have all 8 special actions
    assert len(special_actions) == 8

    # Test each special action ID exists
    action_ids = [action.id for action in special_actions]
    expected_ids = [
        SpecialActionId.GOTO,
        SpecialActionId.SCRAPE,
        SpecialActionId.SCREENSHOT,
        SpecialActionId.BACK,
        SpecialActionId.FORWARD,
        SpecialActionId.REFRESH,
        SpecialActionId.WAIT,
        SpecialActionId.TERMINATE,
    ]
    assert sorted(action_ids) == sorted(expected_ids)

    # Test special action detection
    for action_id in expected_ids:
        assert SpecialAction.is_special(action_id)

    # Test non-special action detection
    assert not SpecialAction.is_special("B1")
    assert not SpecialAction.is_special("I1")
    assert not SpecialAction.is_special("L1")


@pytest.mark.asyncio
async def test_special_actions_execution(llm_service: MockLLMService):
    """Test the execution of various special actions"""
    async with NotteEnv(headless=True, llmserve=llm_service, screenshot=False) as env:
        # Test S1: Go to URL
        obs = await env.execute(SpecialActionId.GOTO, {"url": "https://notte.cc/"})
        assert obs.clean_url == "notte.cc"

        # Test S2: Scrape data
        obs = await env.execute(SpecialActionId.SCRAPE)
        assert obs.data is not None
        assert obs.data.markdown == "# Hello World"

        # Test S3: Take screenshot
        obs = await env.execute(SpecialActionId.SCREENSHOT)
        assert obs.screenshot is not None

        # Test S4: Go back
        obs = await env.execute(SpecialActionId.GOTO, {"url": "https://google.com/"})
        assert obs.clean_url == "google.com"
        obs = await env.execute(SpecialActionId.BACK)
        assert obs.clean_url == "notte.cc"

        # Test S5: Go forward
        obs = await env.execute(SpecialActionId.FORWARD)
        assert obs.clean_url == "google.com"

        # Test S7: Wait
        _ = await env.execute("S7", {"value": "1"})

        # Test S8: Terminate session (cannot execute any actions after this)
        _ = await env.execute("S8")
        with pytest.raises(RuntimeError, match="Browser not started"):
            _ = await env.goto("https://example.com/")


@pytest.mark.asyncio
async def test_special_action_validation(llm_service: MockLLMService):
    """Test validation of special action parameters"""
    async with NotteEnv(headless=True, llmserve=llm_service) as env:
        _ = await env.goto("https://notte.cc/")
        # Test S1 requires URL parameter
        with pytest.raises(ValueError, match=f"Special action {SpecialActionId.GOTO} requires a parameter"):
            _ = await env.execute(SpecialActionId.GOTO)

        # Test S7 requires wait time parameter
        with pytest.raises(ValueError, match=f"Special action {SpecialActionId.WAIT} requires a parameter"):
            _ = await env.execute(SpecialActionId.WAIT)

        # Test invalid special action
        with pytest.raises(ValueError, match="action X1 not found in context"):
            _ = await env.execute("X1")
