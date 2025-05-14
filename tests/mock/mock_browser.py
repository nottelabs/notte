from dataclasses import dataclass
from typing import final

from loguru import logger
from notte_core.actions.percieved import ExecPerceivedAction
from notte_core.browser.dom_tree import A11yNode, A11yTree, ComputedDomAttributes, DomNode
from notte_core.browser.node_type import NodeType
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, TabsData, ViewportData
from notte_core.common.resource import AsyncResource
from typing_extensions import TypedDict, override


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

        self._mock_dom_node = DomNode(
            id="mock",
            role="WebArea",
            text="Mock WebArea",
            children=[
                DomNode(
                    id="L1",
                    role="link",
                    text="More information",
                    children=[],
                    attributes=None,
                    computed_attributes=ComputedDomAttributes(),
                    type=NodeType.INTERACTION,
                ),
            ],
            attributes=None,
            computed_attributes=ComputedDomAttributes(),
            type=NodeType.OTHER,
        )

        self._mock_snapshot = BrowserSnapshot(
            metadata=SnapshotMetadata(
                title="mock",
                url="https://mock.url",
                viewport=ViewportData(
                    scroll_x=0,
                    scroll_y=0,
                    viewport_width=1000,
                    viewport_height=1000,
                    total_width=1000,
                    total_height=1000,
                ),
                tabs=[
                    TabsData(
                        tab_id=0,
                        title="mock",
                        url="https://mock.url",
                    ),
                ],
            ),
            html_content="<html><body>Mock HTML</body></html>",
            a11y_tree=self._mock_tree,
            screenshot=None,
            dom_node=self._mock_dom_node,
        )
        super().__init__()

    @override
    async def start(self) -> None:
        """Mock browser startup"""
        pass

    @override
    async def stop(self) -> None:
        """Mock browser cleanup"""
        pass

    async def snapshot(self, screenshot: bool | None = None) -> BrowserSnapshot:
        """Return a mock browser snapshot"""
        return self._mock_snapshot

    async def reset(self) -> None:
        """Mock browser reset"""
        pass

    async def press(self, key: str = "Enter") -> BrowserSnapshot:
        """Mock key press action"""
        return self._mock_snapshot

    async def goto(self, url: str, wait_for: str = "networkidle") -> BrowserSnapshot:
        """Mock navigation action"""
        snapshot = BrowserSnapshot(
            metadata=SnapshotMetadata(
                title="mock",
                url=url,
                viewport=ViewportData(
                    scroll_x=0,
                    scroll_y=0,
                    viewport_width=1000,
                    viewport_height=1000,
                    total_width=1000,
                    total_height=1000,
                ),
                tabs=[
                    TabsData(
                        tab_id=0,
                        title="mock",
                        url=url,
                    ),
                ],
            ),
            html_content="<html><body>Mock HTML</body></html>",
            a11y_tree=self._mock_tree,
            screenshot=None,
            dom_node=self._mock_dom_node,
        )
        return snapshot

    async def execute_action(
        self,
        action: ExecPerceivedAction,
        snapshot: BrowserSnapshot,
        enter: bool = False,
    ) -> BrowserSnapshot:
        """Mock action execution"""
        if enter:
            await self.press("Enter")
        return self._mock_snapshot

    @property
    def page(self) -> MockBrowserPage:
        return MockBrowserPage()
