import pytest
from notte_browser.session import NotteSession
from notte_core.actions import GotoAction

from tests.mock.mock_browser import MockBrowserDriver


@pytest.mark.asyncio
async def test_execute_does_not_append_a_screenshot() -> None:
    async with NotteSession(window=MockBrowserDriver()) as session:
        _ = await session.aexecute(GotoAction(url="https://www.example.com"))
        _ = await session.aexecute(GotoAction(url="https://www.example.com"))

        assert len(list(session.trajectory.execution_results())) == 2
        assert list(session.trajectory.screenshots()) == []
        assert session.trajectory.last_screenshot is None


@pytest.mark.asyncio
async def test_explicit_screenshot_is_appended_to_the_trajectory() -> None:
    async with NotteSession(window=MockBrowserDriver()) as session:
        _ = await session.aexecute(GotoAction(url="https://www.example.com"))
        screenshot = await session.ascreenshot()

        assert list(session.trajectory.screenshots()) == [screenshot]
        assert session.trajectory.last_screenshot is screenshot
