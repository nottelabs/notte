from collections.abc import Awaitable
from typing import Literal, NotRequired, TypedDict, Unpack

from loguru import logger
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from notte.actions.base import ExecutableAction
from notte.actions.executor import ActionExecutor, get_executor
from notte.browser.context import Context
from notte.browser.node_type import A11yNode, A11yTree
from notte.browser.pool import BrowserPool, BrowserResource
from notte.browser.snapshot import BrowserSnapshot, SnapshotMetadata
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
from notte.utils.url import is_valid_url


class BrowserArgs(TypedDict):
    pool: NotRequired[BrowserPool | None]
    headless: NotRequired[bool]
    timeout: NotRequired[int]
    screenshot: NotRequired[bool | None]


DEFAULT_LOADING_TIMEOUT = 15000
DEFAULT_WAITING_TIMEOUT = 1000


class PlaywrightResource:

    def __init__(self, **kwargs: Unpack[BrowserArgs]) -> None:
        self.shared_pool: bool = kwargs.get("pool") is not None
        if not self.shared_pool:
            logger.info(
                (
                    "Using local browser pool. Consider using a shared pool for better "
                    "resource management and performance by setting `browser_pool=BrowserPool(verbose=True)`"
                )
            )
        self.browser_pool: BrowserPool = kwargs.get("pool") or BrowserPool()
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
            raise BrowserNotStartedError()
        if retries <= 0:
            raise EmptyPageContentError(url=self.page.url, nb_retries=retries)
        try:
            html_content = await self.page.content()
            a11y_simple: A11yNode | None = await self.page.accessibility.snapshot()  # type: ignore
            a11y_raw: A11yNode | None = await self.page.accessibility.snapshot(interesting_only=False)  # type: ignore
        except Exception as e:
            if "has been closed" in str(e):
                raise BrowserExpiredError() from e
            raise UnexpectedBrowserError(url=self.page.url) from e
        if a11y_simple is None or a11y_raw is None or len(a11y_simple.get("children", [])) == 0:
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
            a11y_tree=A11yTree(
                simple=a11y_simple,
                raw=a11y_raw,
            ),
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
        wait_for: Literal["domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> BrowserSnapshot:
        if not self.page:
            raise BrowserNotStartedError()
        if url is None or url == self.page.url:
            return await self.snapshot()
        if not is_valid_url(url, check_reachability=False):
            raise InvalidURLError(url=url)
        try:
            _ = await self.page.goto(url)
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
                "page", timeout=self._playwright.timeout
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
        context: Context,
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
