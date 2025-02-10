import time
from collections.abc import Awaitable

from loguru import logger
from patchright.async_api import Page
from patchright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel

from notte.actions.base import ExecutableAction
from notte.actions.executor import ActionExecutor, get_executor
from notte.browser.dom_tree import A11yNode, A11yTree, DomNode
from notte.browser.pool import BrowserPool, BrowserResource
from notte.browser.processed_snapshot import ProcessedBrowserSnapshot
from notte.browser.snapshot import (
    BrowserSnapshot,
    SnapshotMetadata,
    TabsData,
    ViewportData,
)
from notte.common.resource import AsyncResource
from notte.errors.actions import ActionExecutionError
from notte.errors.browser import (
    BrowserExpiredError,
    BrowserNotStartedError,
    EmptyPageContentError,
    InvalidURLError,
    PageLoadingError,
    UnexpectedBrowserError,
)
from notte.pipe.preprocessing.dom.parsing import ParseDomTreePipe
from notte.utils.url import is_valid_url


class BrowserConfig(BaseModel):
    headless: bool = False
    goto_timeout: int = 10000
    goto_retry_timeout: int = 1000
    retry_timeout: int = 1000
    step_timeout: int = 1000
    short_wait_timeout: int = 500
    screenshot: bool | None = True
    empty_page_max_retry: int = 5


class PlaywrightResource:

    def __init__(self, pool: BrowserPool | None, config: BrowserConfig) -> None:
        self.config: BrowserConfig = config
        self.shared_pool: bool = pool is not None
        if not self.shared_pool:
            logger.info(
                "Using local browser pool. Con  sider using a shared pool for better "
                "resource management and performance by setting `browser_pool=BrowserPool(verbose=True)`"
            )
        self.browser_pool: BrowserPool = pool or BrowserPool()
        self._page: Page | None = None
        self._resource: BrowserResource | None = None

    async def start(self) -> None:
        # Get or create a browser from the pool
        self._resource = await self.browser_pool.get_browser_resource(self.config.headless)
        # Create and track a new context
        self._resource.page.set_default_timeout(self.config.step_timeout)

    async def close(self) -> None:
        if self._resource is not None:
            # Remove context from tracking
            await self.browser_pool.release_browser_resource(self._resource)
            self._resource = None
        if not self.shared_pool:
            await self.browser_pool.cleanup(force=True)
            await self.browser_pool.stop()

    @property
    def page(self) -> Page:
        if self._resource is None:
            raise BrowserNotStartedError()
        return self._resource.page


class BrowserDriver(AsyncResource):

    def __init__(
        self,
        pool: BrowserPool | None = None,
        config: BrowserConfig | None = None,
    ) -> None:
        self._playwright: PlaywrightResource = PlaywrightResource(pool, config or BrowserConfig())
        super().__init__(self._playwright)

    @property
    def page(self) -> Page:
        return self._playwright.page

    async def reset(self) -> None:
        await self.close()
        await self.start()

    async def long_wait(self) -> None:
        start_time = time.time()
        try:
            await self.page.wait_for_load_state("networkidle", timeout=self._playwright.config.goto_timeout)
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout while waiting for networkidle state for '{self.page.url}'")
        await self.short_wait()
        # await self.page.wait_for_timeout(self._playwright.config.step_timeout)
        logger.info(f"Waited for networkidle state for '{self.page.url}' in {time.time() - start_time:.2f}s")

    async def short_wait(self) -> None:
        await self.page.wait_for_timeout(self._playwright.config.short_wait_timeout)

    async def snapshot(self, screenshot: bool | None = None, retries: int | None = None) -> BrowserSnapshot:
        # logger.error(f"Taking snapshot of {self.page.url}")
        if not self.page:
            raise BrowserNotStartedError()
        if retries is None:
            retries = self._playwright.config.empty_page_max_retry
        if retries <= 0:
            raise EmptyPageContentError(url=self.page.url, nb_retries=self._playwright.config.empty_page_max_retry)
        html_content: str = ""
        a11y_simple: A11yNode | None = None
        a11y_raw: A11yNode | None = None
        dom_node: DomNode | None = None
        try:
            html_content = await self.page.content()
            a11y_simple = await self.page.accessibility.snapshot()  # type: ignore
            a11y_raw = await self.page.accessibility.snapshot(interesting_only=False)  # type: ignore
            dom_node = await ParseDomTreePipe.forward(self.page)
        except Exception as e:
            if "has been closed" in str(e):
                raise BrowserExpiredError() from e
            if "Unable to retrieve content because the page is navigating and changing the content" in str(e):
                # Should retry after the page is loaded
                await self.short_wait()
            else:
                raise UnexpectedBrowserError(url=self.page.url) from e
        if dom_node is None or a11y_simple is None or a11y_raw is None or len(a11y_simple.get("children", [])) == 0:
            logger.warning(f"Empty page content for {self.page.url}. Retry in {self._playwright.config.step_timeout}ms")
            await self.page.wait_for_timeout(self._playwright.config.goto_retry_timeout)
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)
        take_screenshot = screenshot if screenshot is not None else self._playwright.config.screenshot
        try:
            snapshot_screenshot = await self.page.screenshot() if take_screenshot else None
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout while taking screenshot for {self.page.url}. Retrying...")
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)

        return BrowserSnapshot(
            metadata=SnapshotMetadata(
                title=await self.page.title(),
                url=self.page.url,
                viewport=ViewportData(
                    scroll_x=int(await self.page.evaluate("window.scrollX")),
                    scroll_y=int(await self.page.evaluate("window.scrollY")),
                    viewport_width=int(await self.page.evaluate("window.innerWidth")),
                    viewport_height=int(await self.page.evaluate("window.innerHeight")),
                    total_width=int(await self.page.evaluate("document.documentElement.scrollWidth")),
                    total_height=int(await self.page.evaluate("document.documentElement.scrollHeight")),
                ),
                tabs=[
                    TabsData(
                        tab_id=i,
                        title=await page.title(),
                        url=page.url,
                    )
                    for i, page in enumerate(self._playwright.page.context.pages)
                ],
            ),
            html_content=html_content,
            a11y_tree=A11yTree(
                simple=a11y_simple,
                raw=a11y_raw,
            ),
            dom_node=dom_node,
            screenshot=snapshot_screenshot,
        )

    async def press(self, key: str = "Enter") -> BrowserSnapshot:
        if not self.page:
            raise BrowserNotStartedError()
        await self.page.keyboard.press(key)
        # update context
        await self.short_wait()
        return await self.snapshot()

    async def goto(
        self,
        url: str | None = None,
    ) -> BrowserSnapshot:
        if not self.page:
            raise BrowserNotStartedError()
        if url is None or url == self.page.url:
            return await self.snapshot()
        if not is_valid_url(url, check_reachability=False):
            raise InvalidURLError(url=url)
        try:
            _ = await self.page.goto(url, timeout=self._playwright.config.goto_timeout)
            await self.page.wait_for_load_state(timeout=self._playwright.config.goto_timeout)
        except Exception as e:
            raise PageLoadingError(url=url) from e
        await self.long_wait()
        return await self.snapshot()

    async def handle_possible_new_tab(
        self,
        action_executor: ActionExecutor,
    ) -> tuple[bool, Page | None]:
        """
        Executes an action and handles potential new tab creation.

        Args:
            page: Current page
            action: Async function to execute that might open a new tab
            timeout: Maximum time to wait for new tab in milliseconds

        Returns:
            Tuple of (action result, active page to use for next actions)
        """
        try:
            # Start listening for new pages
            new_page_promise: Awaitable[Page] = self.page.context.wait_for_event(
                "page", timeout=self._playwright.config.step_timeout
            )

            # Execute the action that might open a new tab
            success = await action_executor(self.page)

            try:
                # Wait to see if a new page was created
                new_page: Page = await new_page_promise
                await new_page.wait_for_load_state()
                return success, new_page
            except TimeoutError:
                # No new page was created, continue with current page
                return success, None

        except TimeoutError:
            # No new page was created, continue with current page
            return False, None

    async def execute_action(
        self,
        action: ExecutableAction,
        context: ProcessedBrowserSnapshot,
        enter: bool = False,
    ) -> BrowserSnapshot:
        """Execute action in async mode"""
        if not self.page:
            raise BrowserNotStartedError()
        if self.page.url != context.snapshot.metadata.url:
            raise ActionExecutionError(
                action_id=action.id,
                url=self.page.url,
                reason=(
                    "browser is not on the correct page. Use `goto` to navigate to "
                    f"{context.snapshot.metadata.url} and retry the action execution."
                ),
            )
        action_executor = get_executor(action)
        is_success = await action_executor(self.page)
        if not is_success:
            logger.error(f"Execution code that failed: {action.code}")
            raise ActionExecutionError(action_id=action.id, url=self.page.url)
        # TODO: find a better way to wait for the page to be updated
        await self.short_wait()
        if enter:
            return await self.press("Enter")
        return await self.snapshot()
