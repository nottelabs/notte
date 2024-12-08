from typing import NotRequired, TypedDict, Unpack

from notte.actions.base import ExecutableAction
from notte.actions.executor import get_executor
from notte.browser.context import Context
from notte.browser.node_type import A11yTree
from notte.browser.snapshot import BrowserSnapshot
from notte.common.resource import AsyncResource
from playwright.async_api import Page, Playwright, async_playwright


class BrowserArgs(TypedDict):
    headless: NotRequired[bool]
    persist: NotRequired[bool]
    timeout: NotRequired[int]
    screenshot: NotRequired[bool]


class PlaywrightResource:

    def __init__(self, **kwargs: Unpack[BrowserArgs]) -> None:
        self.playwright: Playwright | None = None
        self.args: BrowserArgs = kwargs
        self._page: Page | None = None
        self._playwright: Playwright | None = None

    async def start(self) -> None:
        self.playwright = await async_playwright().start()
        browser = await self.playwright.chromium.launch(headless=self.args["headless"])
        context = await browser.new_context()
        self._page = await context.new_page()
        self._page.set_default_timeout(self.args["timeout"])

    async def close(self) -> None:
        if self.args["persist"]:
            return
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
        headless: bool = False,
        persist: bool = False,
        timeout: int = 10000,
        screenshot: bool = True,
    ) -> None:
        self._playwright: PlaywrightResource = PlaywrightResource(
            headless=headless, persist=persist, timeout=timeout, screenshot=screenshot
        )
        self._screenshot: bool = screenshot
        super().__init__(self._playwright)

    @property
    def page(self) -> Page:
        return self._playwright.page

    async def snapshot(self) -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")

        html_content = await self.page.content()
        a11y_tree = A11yTree(
            simple=await self.page.accessibility.snapshot(),
            raw=await self.page.accessibility.snapshot(interesting_only=False),
        )

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
        await self.page.wait_for_timeout(500)
        return await self.snapshot()

    async def goto(self, url: str, wait_for: str = "networkidle") -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        _ = await self.page.goto(url)
        await self.page.wait_for_load_state(wait_for)
        await self.page.wait_for_timeout(500)

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
        await self.page.wait_for_timeout(500)
        if enter:
            _ = await self.press("Enter")
            await self.page.wait_for_timeout(500)
        return await self.snapshot()
