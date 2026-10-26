from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, final

from loguru import logger
from notte_browser.driver import Page, Request, Response
from notte_browser.settle import SINCE_LOAD_JS, _PageState
from notte_browser.window import ScreenshotMask
from notte_core.dom_tree import ComputedDomAttributes, DomAttributes, DomNode, NodeSelectors
from notte_core.node_type import NodeType
from notte_core.observation import Observation
from notte_core.resource import AsyncResource
from notte_core.snapshot import BrowserSnapshot, SnapshotMetadata, TabsData, ViewportData
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


class MockBrowserContext:
    @property
    def pages(self) -> list[Any]:
        return []

    def on(self, event: str, handler: Callable[[Page], None] | Callable[[Request], None]) -> None:
        pass

    def remove_listener(self, event: str, handler: Callable[[Page], None] | Callable[[Request], None]) -> None:
        pass


class MockSettleTracker:
    """The settle tracker (`notte_browser.settle`) of a page where nothing happens: settled at once."""

    async def evaluate(self, expression: str) -> _PageState | None:
        if "state" in expression:
            return {"elapsed": 10_000, "first": None, "last": None, "dom": None, "urlAt": None, "inputAt": None}
        return None

    async def dispose(self) -> None:
        pass


class MockBrowserPage:
    def __init__(self, url: str = "about:blank"):
        self.url: str = url

    def on(self, event: str, handler: Callable[[Request], None]) -> None:
        pass

    def remove_listener(self, event: str, handler: Callable[[Request], None]) -> None:
        pass

    async def evaluate_handle(self, expression: str) -> MockSettleTracker:
        return MockSettleTracker()

    async def evaluate(self, expression: str) -> str | float:
        if expression == "document.readyState":
            return "complete"
        if expression == SINCE_LOAD_JS:
            return 1_000
        raise ValueError(f"Unexpected page evaluation: {expression}")

    def locate(self, selector: str) -> MockLocator:
        return MockLocator(name="mock", role="mock", selector=selector)

    def get_by_role(self, role: str, name: str | None = None) -> MockLocator:
        return MockLocator(name=name, role=role, selector=f"role={role}&name={name}")

    @property
    def context(self) -> MockBrowserContext:
        return MockBrowserContext()


@final
class MockBrowserDriver(AsyncResource):
    """A mock browser that mimics the BrowserDriver API but returns mock data"""

    def __init__(
        self, headless: bool = True, timeout: int = 10000, screenshot: bool = False, url: str = "about:blank"
    ) -> None:
        self.args = MockBrowserDriverArgs(
            headless=headless,
            timeout=timeout,
            screenshot=screenshot,
        )
        # Mirrors BrowserWindow.screenshot_mask (set by the session when a vault is attached).
        self.screenshot_mask: ScreenshotMask | None = None
        self.goto_response: Response | None = None

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
                    attributes=DomAttributes.safe_init(tag_name="a"),
                    computed_attributes=ComputedDomAttributes(
                        selectors=NodeSelectors.from_unique_selector('internal:role=link[name="More information"i]'),
                    ),
                    type=NodeType.INTERACTION,
                ),
            ],
            attributes=DomAttributes.safe_init(tag_name="div"),
            computed_attributes=ComputedDomAttributes(
                selectors=NodeSelectors.from_unique_selector('internal:role=link[name="More information"i]'),
            ),
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
            screenshot=Observation.empty().screenshot.raw,
            dom_node=self._mock_dom_node,
        )
        self.url: str = url
        super().__init__()

    @override
    async def astart(self) -> None:
        """Mock browser startup"""
        pass

    @override
    async def astop(self) -> None:
        """Mock browser cleanup"""
        pass

    @override
    async def areset(self) -> None:
        """Mock browser reset"""
        pass

    async def screenshot(self) -> bytes:
        """Mock browser screenshot"""
        return Observation.empty().screenshot.raw

    async def goto(self, url: str, wait_until: str | None = None) -> BrowserSnapshot:
        """Mock navigation action"""
        self.url = url
        self.wait_until = wait_until
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
            screenshot=Observation.empty().screenshot.raw,
            dom_node=self._mock_dom_node,
        )
        self._mock_snapshot = snapshot
        return snapshot

    async def short_wait(self) -> None:
        pass

    async def long_wait(self) -> None:
        pass

    async def close(self) -> None:
        pass

    @property
    def page(self) -> MockBrowserPage:
        return MockBrowserPage(url=self.url)

    async def snapshot(self) -> BrowserSnapshot:
        return self._mock_snapshot
