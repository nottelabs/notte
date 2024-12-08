from typing import TypedDict, final

from notte.actions.base import ExecutableAction
from notte.browser.context import Context
from notte.browser.node_type import A11yNode, A11yTree
from notte.browser.snapshot import BrowserSnapshot
from notte.common.resource import AsyncResource
from typing_extensions import override


class MockBrowserDriverArgs(TypedDict):
    headless: bool
    persist: bool
    timeout: int
    screenshot: bool


@final
class MockBrowserDriver(AsyncResource):
    """A mock browser that mimics the BrowserDriver API but returns mock data"""

    def __init__(
        self,
        headless: bool = True,
        persist: bool = False,
        timeout: int = 10000,
        screenshot: bool = False,
    ) -> None:
        self.args = MockBrowserDriverArgs(
            headless=headless,
            persist=persist,
            timeout=timeout,
            screenshot=screenshot,
        )
        self._mock_a11y_node = A11yNode(
            role="mock",
            name="mock",
            children=[],
        )
        self._mock_tree = A11yTree(
            simple=self._mock_a11y_node,
            raw=self._mock_a11y_node,
        )
        self._mock_snapshot = BrowserSnapshot(
            url="https://mock.url",
            html_content="<html><body>Mock HTML</body></html>",
            a11y_tree=self._mock_tree,
            screenshot=None,
        )
        super().__init__(self)

    @override
    async def start(self) -> None:
        """Mock browser startup"""
        pass

    @override
    async def close(self) -> None:
        """Mock browser cleanup"""
        pass

    async def snapshot(self) -> BrowserSnapshot:
        """Return a mock browser snapshot"""
        return self._mock_snapshot

    async def press(self, key: str = "Enter") -> BrowserSnapshot:
        """Mock key press action"""
        return self._mock_snapshot

    async def goto(self, url: str, wait_for: str = "networkidle") -> BrowserSnapshot:
        """Mock navigation action"""
        snapshot = BrowserSnapshot(
            url=url,  # Use the provided URL
            html_content="<html><body>Mock HTML</body></html>",
            a11y_tree=self._mock_tree,
            screenshot=None,
        )
        return snapshot

    async def execute_action(
        self,
        action: ExecutableAction,
        context: Context,
        enter: bool = False,
    ) -> BrowserSnapshot:
        """Mock action execution"""
        if enter:
            await self.press("Enter")
        return self._mock_snapshot
