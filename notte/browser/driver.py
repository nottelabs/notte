from typing import Literal, NotRequired, TypedDict, Unpack

from loguru import logger
from playwright.async_api import Page, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from notte.actions.base import ExecutableAction
from notte.actions.executor import get_executor
from notte.browser.context import Context
from notte.browser.node_type import A11yTree
from notte.browser.snapshot import BrowserSnapshot
from notte.common.resource import AsyncResource


class BrowserArgs(TypedDict):
    headless: NotRequired[bool]
    timeout: NotRequired[int]
    screenshot: NotRequired[bool]


DEFAULT_LOADING_TIMEOUT = 15000
DEFAULT_WAITING_TIMEOUT = 500


class PlaywrightResource:

    def __init__(self, **kwargs: Unpack[BrowserArgs]) -> None:
        self.playwright: Playwright | None = None
        self.args: BrowserArgs = kwargs
        self._page: Page | None = None
        self._playwright: Playwright | None = None
        self.timeout: int = kwargs.get("timeout", DEFAULT_LOADING_TIMEOUT)
        self.headless: bool = kwargs.get("headless", False)

    async def start(self) -> None:
        self.playwright = await async_playwright().start()
        browser = await self.playwright.chromium.launch(headless=self.headless)
        context = await browser.new_context()
        self._page = await context.new_page()
        self._page.set_default_timeout(self.timeout)

    async def close(self) -> None:
        await self.page.close()
        if self.playwright:
            await self.playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Page not initialized. Call `start` first.")
        return self._page


class BrowserDriver(AsyncResource):

    def __init__(
        self,
        **browser_args: Unpack[BrowserArgs],
    ) -> None:
        self._playwright: PlaywrightResource = PlaywrightResource(**browser_args)
        self._screenshot: bool = browser_args.get("screenshot", True)
        super().__init__(self._playwright)

    @property
    def page(self) -> Page:
        return self._playwright.page

    async def snapshot(self, retries: int = 5) -> BrowserSnapshot:
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
            await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
            return await self.snapshot(retries=retries - 1)

        screenshot = await self.page.screenshot() if self._screenshot else None
        return BrowserSnapshot(
            url=self.page.url,
            html_content=html_content,
            a11y_tree=a11y_tree,
            screenshot=screenshot,
        )

    async def press(self, key: str = "Enter") -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        await self.page.keyboard.press(key)
        # update context
        await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
        return await self.snapshot()

    async def goto(
        self,
        url: str,
        wait_for: Literal["domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        _ = await self.page.goto(url)
        try:
            await self.page.wait_for_load_state(wait_for, timeout=self._playwright.timeout)
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout while waiting for {wait_for} state for '{url}'")
        await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
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
        if self.page.url != context.snapshot.url:
            raise ValueError(("Browser is not on the expected page. " "Use `goto` to navigate to the expected page."))
        action_executor = get_executor(action)
        await action_executor(self.page)
        # TODO: find a better way to wait for the page to be updated
        await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
        if enter:
            _ = await self.press("Enter")
            await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
        return await self.snapshot()
