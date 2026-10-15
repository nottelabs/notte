import pytest
from notte_browser.errors import ScrollActionFailedError
from notte_browser.session import NotteSession
from notte_core.actions import BrowserAction, ClickAction
from notte_core.browser.observation import ExecutionResult
from notte_core.errors import ErrorConfig


def test_browser_actions_list():
    """Test that all special actions are properly defined"""
    browser_actions = BrowserAction.list()

    # Every registered browser action is listed, except the legacy agent-loop actions, inbox reads and API-only actions
    expected_ids = set(BrowserAction.BROWSER_ACTION_REGISTRY.keys()) - BrowserAction.unlisted_action_types()
    assert len(browser_actions) == len(expected_ids)

    # Test each special action ID exists
    action_ids = set([action.type for action in browser_actions])
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
        _ = await page.aexecute(type="goto", url="https://example.com/")
        obs = await page.aobserve()
        assert obs.clean_url == "example.com"

        example_com_str = "This domain is for use in documentation examples without needing permission."

        # Test S2: Scrape data
        markdown = await page.ascrape()
        assert example_com_str in markdown.strip(), (
            f"Expected typical example.com str, got: \n ```markdown\n{markdown}\n```"
        )


@pytest.mark.asyncio
async def test_go_back_and_forward():
    """Test the execution of various special actions"""
    async with NotteSession(headless=True) as page:
        # Test S4: Go to notte
        _ = await page.aexecute(type="goto", url="https://github.com/")
        obs = await page.aobserve()
        assert obs.clean_url == "github.com"
        # Test S4: Go back
        _ = await page.aexecute(type="goto", url="https://notte.cc/")
        obs = await page.aobserve()
        assert "notte.cc" in obs.clean_url
        _ = await page.aexecute(type="go_back")
        obs = await page.aobserve()
        assert obs.clean_url == "github.com"

        # Test S5: Go forward
        _ = await page.aexecute(type="go_forward")
        obs = await page.aobserve()
        assert "notte.cc" in obs.clean_url


@pytest.mark.asyncio
async def test_wait_and_complete():
    """Test the execution of various special actions"""
    async with NotteSession(headless=True) as page:
        # Test S4: Go goto goole
        _ = await page.aexecute(type="goto", url="https://www.google.com/")
        obs = await page.aobserve()

        assert "google.com" in obs.clean_url

        # Test S7: Wait
        _ = await page.aexecute(type="wait", time_ms=1)

        _ = await page.aobserve()


@pytest.mark.asyncio
async def test_special_action_validation():
    """Test validation of special action parameters"""
    async with NotteSession(headless=True, raise_on_failure=False) as page:
        _ = await page.aexecute(type="goto", url="https://github.com/")
        _ = await page.aobserve()
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
        result = await page.aexecute(type="click", id="X1")
        check_failure(result)

        result = await page.aexecute(ClickAction(id="X1"))
        check_failure(result)

        result = page.execute(type="click", id="X1")
        check_failure(result)

        result = page.execute(ClickAction(id="X1"))
        check_failure(result)


@pytest.mark.asyncio
async def test_switch_tab():
    """Test the execution of the switch tab action"""
    with NotteSession(headless=True) as page:
        _ = await page.aexecute(type="goto", url="https://github.com/")
        obs = await page.aobserve()
        assert len(obs.metadata.tabs) == 1
        assert obs.clean_url == "github.com"

        _ = await page.aexecute(
            type="goto_new_tab",
            url="https://www.google.com/",
        )
        obs = await page.aobserve()
        assert len(obs.metadata.tabs) == 2
        assert "google.com" in obs.clean_url

        _ = page.execute(type="switch_tab", tab_index=0)
        obs = await page.aobserve()
        assert obs.clean_url == "github.com"

        _ = page.execute(type="switch_tab", tab_index=1)
        obs = await page.aobserve()
        assert "google.com" in obs.clean_url


@pytest.mark.asyncio
async def test_scroll_on_non_scrollable_page_should_fail():
    assert ErrorConfig.get_message_mode().value == "developer"
    async with NotteSession(raise_on_failure=False) as session:
        assert ErrorConfig.get_message_mode().value == "developer"
        _ = await session.aexecute(type="goto", url="https://www.google.com/")
        _ = await session.aobserve()
        assert ErrorConfig.get_message_mode().value == "developer"
        res = await session.aexecute(type="scroll_down")
        assert not res.success
        assert isinstance(res.exception, ScrollActionFailedError)
        assert res.message == ScrollActionFailedError().dev_message


@pytest.mark.asyncio
async def test_scroll_on_scrollable_page_should_succeed():
    async with NotteSession(browser_type="chrome") as session:
        res = await session.aexecute(type="goto", url="https://duckduckgo.com/")
        assert res.success
        obs = await session.aobserve()
        res = await session.aexecute(type="scroll_down")
        obs2 = await session.aobserve()
        assert res.success, f"Viewport obs2: {obs2.metadata.viewport}"
        assert obs.metadata.viewport.scroll_x == obs2.metadata.viewport.scroll_x
        assert obs.metadata.viewport.scroll_y != obs2.metadata.viewport.scroll_y
        res = await session.aexecute(type="scroll_up")
        assert res.success
        obs3 = await session.aobserve()
        assert obs3.metadata.viewport.scroll_x == obs2.metadata.viewport.scroll_x
        assert obs3.metadata.viewport.scroll_y != obs2.metadata.viewport.scroll_y
        assert obs3.metadata.viewport.scroll_y == obs.metadata.viewport.scroll_y


@pytest.mark.asyncio
async def test_evaluate_js_action():
    """Test the evaluate_js action returns correct results"""
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url="https://example.com")

        # Test getting page title via evaluate_js
        result = await session.aexecute(type="evaluate_js", code="document.title")
        assert result.success
        assert result.data is not None
        assert "Example Domain" in result.data.markdown

        # Test getting structured data (array of links)
        result = await session.aexecute(
            type="evaluate_js",
            code="Array.from(document.querySelectorAll('a')).map(a => ({href: a.href, text: a.innerText}))",
        )
        assert result.success
        assert result.data is not None
        # Result should be JSON array
        assert "[" in result.data.markdown
        assert "href" in result.data.markdown

        # Test returning a simple number
        result = await session.aexecute(type="evaluate_js", code="document.querySelectorAll('p').length")
        assert result.success
        assert result.data is not None
        # Should be a number as string
        assert result.data.markdown.isdigit()
