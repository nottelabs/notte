from typing import Literal, NotRequired, TypedDict, Unpack

from loguru import logger
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from notte.actions.base import ExecutableAction
from notte.actions.executor import get_executor
from notte.browser.context import Context
from notte.browser.node_type import A11yTree
from notte.browser.pool import BrowserPool, BrowserResource
from notte.browser.snapshot import BrowserSnapshot, SnapshotMetadata
from notte.common.resource import AsyncResource
from notte.utils.url import is_valid_url


class BrowserArgs(TypedDict):
    headless: NotRequired[bool]
    timeout: NotRequired[int]
    screenshot: NotRequired[bool | None]


DEFAULT_LOADING_TIMEOUT = 15000
DEFAULT_WAITING_TIMEOUT = 1000


class PlaywrightResource:
    browser_pool: BrowserPool = BrowserPool()

    def __init__(self, **kwargs: Unpack[BrowserArgs]) -> None:
        self.args: BrowserArgs = kwargs
        self._page: Page | None = None
        self.timeout: int = kwargs.get("timeout", DEFAULT_LOADING_TIMEOUT)
        self.headless: bool = kwargs.get("headless", False)
        self._resource: BrowserResource | None = None

    async def start(self) -> None:
        # Get or create a browser from the pool
        self._resource = await self.browser_pool.get_browser_resource(self.headless)
        # Create and track a new context
        self._resource.page.set_default_timeout(self.timeout)

    async def close(self) -> None:
        if self._resource is not None:
            # Remove context from tracking
            await self.browser_pool.release_browser_resource(self._resource)
            self._resource = None

    @property
    def page(self) -> Page:
        if self._resource is None:
            raise RuntimeError("Browser not initialized. Call `start` first.")
        return self._resource.page


class BrowserDriver(AsyncResource):

    def __init__(
        self,
        **browser_args: Unpack[BrowserArgs],
    ) -> None:
        self._playwright: PlaywrightResource = PlaywrightResource(**browser_args)
        screenshot = browser_args.get("screenshot")
        self._screenshot: bool = screenshot if screenshot is not None else True
        super().__init__(self._playwright)

    @property
    def page(self) -> Page:
        return self._playwright.page

    async def reset(self) -> None:
        await self.close()
        await self.start()

    async def long_wait(self) -> None:
        try:
            await self.page.wait_for_load_state("networkidle", timeout=self._playwright.timeout)
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout while waiting for networkidle state for '{self.page.url}'")
        await self.short_wait()

    async def short_wait(self) -> None:
        await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)

    async def wait(self, seconds: int) -> None:
        await self.page.wait_for_timeout(seconds * 1000)

    async def back(self) -> BrowserSnapshot:
        _ = await self.page.go_back()
        await self.short_wait()
        return await self.snapshot()

    async def forward(self) -> BrowserSnapshot:
        _ = await self.page.go_forward()
        await self.short_wait()
        return await self.snapshot()

    async def refresh(self) -> BrowserSnapshot:
        _ = await self.page.reload()
        await self.long_wait()
        return await self.snapshot()

    async def snapshot(self, screenshot: bool | None = None, retries: int = 5) -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        if retries <= 0:
            raise ValueError("Browser snapshot failed after 5 retries to get a non-empty web page")
        html_content = await self.page.content()
        a11y_tree = A11yTree(
            simple=await self.page.accessibility.snapshot(),  # type: ignore
            raw=await self.page.accessibility.snapshot(interesting_only=False),  # type: ignore
        )
        if len(a11y_tree.simple.get("children", [])) == 0:
            logger.warning(f"Simple tree is empty for page {self.page.url}. Retry in {DEFAULT_WAITING_TIMEOUT}ms")
            await self.short_wait()
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)
        take_screenshot = screenshot if screenshot is not None else self._screenshot
        snapshot_screenshot = await self.page.screenshot() if take_screenshot else None
        return BrowserSnapshot(
            metadata=SnapshotMetadata(
                title=await self.page.title(),
                url=self.page.url,
            ),
            html_content=html_content,
            a11y_tree=a11y_tree,
            screenshot=snapshot_screenshot,
        )

    async def press(self, key: str = "Enter") -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        await self.page.keyboard.press(key)
        # update context
        await self.short_wait()
        return await self.snapshot()

    async def goto(
        self,
        url: str | None = None,
        wait_for: Literal["domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        if url is None or url == self.page.url:
            return await self.snapshot()
        if not is_valid_url(url, check_reachability=False):
            raise ValueError(
                f"Invalid URL: {url}. Check if the URL is reachable. URLs should start with https:// or http://"
            )
        try:
            _ = await self.page.goto(url)
        except Exception as e:
            raise ValueError(f"Failed to navigate to {url}. Check if the URL is reachable.") from e
        await self.long_wait()
        return await self.snapshot()

    async def execute_action(
        self,
        action: ExecutableAction,
        context: Context,
        enter: bool = False,
    ) -> BrowserSnapshot:
        """Execute action in async mode"""
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        if self.page.url != context.snapshot.metadata.url:
            raise ValueError(("Browser is not on the expected page. " "Use `goto` to navigate to the expected page."))
        action_executor = get_executor(action)
        is_success = await action_executor(self.page)
        if not is_success:
            raise ValueError(f"Execution of action '{action.id}' failed")
        # TODO: find a better way to wait for the page to be updated
        await self.short_wait()
        if enter:
            return await self.press("Enter")
        return await self.snapshot()
