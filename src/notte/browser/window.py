import time

from loguru import logger
from patchright.async_api import Page
from patchright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel

from notte.browser.dom_tree import A11yNode, A11yTree, DomNode
from notte.browser.pool.base import BaseBrowserPool, BrowserResource
from notte.browser.pool.cdp_pool import SingleCDPBrowserPool
from notte.browser.pool.local_pool import BrowserPoolConfig, SingleLocalBrowserPool
from notte.browser.snapshot import (
    BrowserSnapshot,
    SnapshotMetadata,
    TabsData,
    ViewportData,
)
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


class BrowserWaitConfig(BaseModel):
    goto: int = 10000
    goto_retry: int = 1000
    retry: int = 1000
    step: int = 1000
    short: int = 500


class BrowserWindowConfig(BaseModel):
    headless: bool = False
    pool: BrowserPoolConfig = BrowserPoolConfig()
    wait: BrowserWaitConfig = BrowserWaitConfig()
    screenshot: bool | None = True
    empty_page_max_retry: int = 5
    cdp_url: str | None = None


def create_browser_pool(config: BrowserWindowConfig) -> BaseBrowserPool:
    if config.cdp_url is not None:
        return SingleCDPBrowserPool(
            cdp_url=config.cdp_url,
            verbose=config.pool.verbose,
        )
    return SingleLocalBrowserPool(config=config.pool)


class BrowserWindow:
    def __init__(
        self,
        pool: BaseBrowserPool | None = None,
        config: BrowserWindowConfig | None = None,
    ) -> None:
        self.config: BrowserWindowConfig = config or BrowserWindowConfig()
        self._pool: BaseBrowserPool = pool or create_browser_pool(self.config)
        self.resource: BrowserResource | None = None

    @property
    def page(self) -> Page:
        if self.resource is None:
            raise BrowserNotStartedError()
        return self.resource.page

    @page.setter
    def page(self, page: Page) -> None:
        if self.resource is None:
            raise BrowserNotStartedError()
        self.resource.page = page

    async def start(self) -> None:
        self.resource = await self._pool.get_browser_resource(headless=self.config.headless)
        # Create and track a new context
        self.resource.page.set_default_timeout(self.config.wait.step)

    async def close(self) -> None:
        if self.resource is not None:
            await self._pool.release_browser_resource(self.resource)
            self.resource = None

    async def long_wait(self) -> None:
        start_time = time.time()
        try:
            await self.page.wait_for_load_state("networkidle", timeout=self.config.wait.goto)
        except PlaywrightTimeoutError:
            if self.config.pool.verbose:
                logger.warning(f"Timeout while waiting for networkidle state for '{self.page.url}'")
        await self.short_wait()
        # await self.page.wait_for_timeout(self._playwright.config.step_timeout)
        if self.config.pool.verbose:
            logger.info(f"Waited for networkidle state for '{self.page.url}' in {time.time() - start_time:.2f}s")

    async def short_wait(self) -> None:
        await self.page.wait_for_timeout(self.config.wait.short)

    async def snapshot_metadata(self) -> SnapshotMetadata:
        return SnapshotMetadata(
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
                for i, page in enumerate(self.page.context.pages)
            ],
        )

    async def snapshot(self, screenshot: bool | None = None, retries: int | None = None) -> BrowserSnapshot:
        if retries is None:
            retries = self.config.empty_page_max_retry
        if retries <= 0:
            raise EmptyPageContentError(url=self.page.url, nb_retries=self.config.empty_page_max_retry)
        html_content: str = ""
        a11y_simple: A11yNode | None = None
        a11y_raw: A11yNode | None = None
        dom_node: DomNode | None = None
        try:
            html_content = await self.page.content()
            a11y_simple = await self.page.accessibility.snapshot()  # type: ignore[attr-defined]
            a11y_raw = await self.page.accessibility.snapshot(interesting_only=False)  # type: ignore[attr-defined]
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
            if self.config.pool.verbose:
                logger.warning(f"Empty page content for {self.page.url}. Retry in {self.config.wait.short}ms")
            await self.page.wait_for_timeout(self.config.wait.short)
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)
        take_screenshot = screenshot if screenshot is not None else self.config.screenshot
        try:
            snapshot_screenshot = await self.page.screenshot() if take_screenshot else None
        except PlaywrightTimeoutError:
            if self.config.pool.verbose:
                logger.warning(f"Timeout while taking screenshot for {self.page.url}. Retrying...")
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)

        return BrowserSnapshot(
            metadata=await self.snapshot_metadata(),
            html_content=html_content,
            a11y_tree=A11yTree(
                simple=a11y_simple,
                raw=a11y_raw,
            ),
            dom_node=dom_node,
            screenshot=snapshot_screenshot,
        )

    async def goto(
        self,
        url: str | None = None,
    ) -> BrowserSnapshot:
        if url is None or url == self.page.url:
            return await self.snapshot()
        if not is_valid_url(url, check_reachability=False):
            raise InvalidURLError(url=url)
        try:
            _ = await self.page.goto(url, timeout=self.config.wait.goto)
        except PlaywrightTimeoutError:
            await self.long_wait()
        except Exception as e:
            raise PageLoadingError(url=url) from e
        # extra wait to make sure that css animations can start
        # to make extra element visible
        await self.short_wait()
        return await self.snapshot()
