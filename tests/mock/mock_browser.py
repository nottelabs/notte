from dataclasses import dataclass
from typing import TypedDict, final

from loguru import logger
from typing_extensions import override

from notte.actions.base import ExecutableAction
from notte.browser.context import Context
from notte.browser.node_type import A11yNode, A11yTree
from notte.browser.snapshot import BrowserSnapshot
from notte.common.resource import AsyncResource


class MockBrowserDriverArgs(TypedDict):
    headless: bool
    timeout: int
    screenshot: bool


@dataclass
class MockLocator:
    name: str
    role: str
    selector: str

    def click(self) -> None:
        logger.info(f"Mock locator {self.name} clicked")

    def fill(self, value: str) -> None:
        logger.info(f"Mock locator {self.name} filled with value: {value}")

    def filter(self, filter_str: str) -> "MockLocator":
        logger.info(f"Mock locator {self.name} filtered with value: {filter_str}")
        return self

    async def all(self) -> list["MockLocator"]:
        logger.info(f"Mock locator {self.name} all")
        return [self]

    def first(self) -> "MockLocator":
        logger.info(f"Mock locator {self.name} first")
        return self

    async def text_content(self) -> str:
        logger.info(f"Mock locator {self.name} text content")
        return "Mock text content"

    async def is_visible(self) -> bool:
        logger.info(f"Mock locator {self.name} is visible")
        return True

    async def is_enabled(self) -> bool:
        logger.info(f"Mock locator {self.name} is enabled")
        return True

    async def is_editable(self) -> bool:
        logger.info(f"Mock locator {self.name} is editable")
        return False

    async def is_checked(self) -> bool:
        logger.info(f"Mock locator {self.name} is checked")
        return False


class MockBrowserPage:

    def locate(self, selector: str) -> MockLocator:
        return MockLocator(name="mock", role="mock", selector=selector)

    def get_by_role(self, role: str, name: str | None = None) -> MockLocator:
        return MockLocator(name=name, role=role, selector=f"role={role}&name={name}")


@final
class MockBrowserDriver(AsyncResource):
    """A mock browser that mimics the BrowserDriver API but returns mock data"""

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 10000,
        screenshot: bool = False,
    ) -> None:
        self.args = MockBrowserDriverArgs(
            headless=headless,
            timeout=timeout,
            screenshot=screenshot,
        )
        self._mock_a11y_node = A11yNode(
            role="WebArea",
            name="",
            children=[
                A11yNode(
                    role="link",
                    name="More information",
                    children=[],
                ),
            ],
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

    @property
    def page(self) -> MockBrowserPage:
        return MockBrowserPage()
