import time
from typing import Any, Callable, ClassVar, Self

import httpx
from loguru import logger
from notte_core.browser.dom_tree import A11yNode, A11yTree, DomNode
from notte_core.browser.snapshot import (
    BrowserSnapshot,
    SnapshotMetadata,
    TabsData,
    ViewportData,
)
from notte_core.common.config import FrozenConfig
from notte_core.errors.processing import SnapshotProcessingError
from notte_core.utils.url import is_valid_url
from notte_sdk.types import BrowserType, Cookie, ProxySettings
from patchright.async_api import CDPSession, Locator, Page
from patchright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, Field
from typing_extensions import override

from notte_browser.dom.parsing import ParseDomTreePipe
from notte_browser.errors import (
    BrowserExpiredError,
    BrowserNotStartedError,
    EmptyPageContentError,
    InvalidURLError,
    PageLoadingError,
    RemoteDebuggingNotAvailableError,
    UnexpectedBrowserError,
)
from notte_browser.resource import (
    BrowserResource,
    BrowserResourceHandler,
    BrowserResourceHandlerConfig,
    BrowserResourceOptions,
    PlaywrightResourceHandler,
)


class BrowserWaitConfig(FrozenConfig):
    # need default values for frozen config
    # so copying them from short
    GOTO: ClassVar[int] = 10_000
    GOTO_RETRY: ClassVar[int] = 1_000
    RETRY: ClassVar[int] = 1_000
    STEP: ClassVar[int] = 1_000
    SHORT_WAIT: ClassVar[int] = 500
    ACTION_TIMEOUT: ClassVar[int] = 1_000

    goto: int = GOTO
    goto_retry: int = GOTO_RETRY
    retry: int = RETRY
    step: int = STEP
    short_wait: int = SHORT_WAIT
    action_timeout: int = ACTION_TIMEOUT

    @classmethod
    def short(cls):
        return cls(
            goto=cls.GOTO,
            goto_retry=cls.GOTO_RETRY,
            retry=cls.RETRY,
            step=cls.STEP,
            short_wait=cls.SHORT_WAIT,
            action_timeout=cls.ACTION_TIMEOUT,
        )

    @classmethod
    def long(cls):
        return cls(goto=10_000, goto_retry=1_000, retry=3_000, step=10_000, short_wait=500, action_timeout=5000)


class BrowserWindowConfig(FrozenConfig):
    # browser options
    headless: bool = False
    proxy: ProxySettings | None = None
    user_agent: str | None = None
    cdp_debug: bool = False
    cookies_path: str | None = None
    cdp_url: str | None = None
    browser_type: BrowserType = BrowserType.CHROMIUM
    # remaining options
    handler: BrowserResourceHandlerConfig = BrowserResourceHandlerConfig()
    wait: BrowserWaitConfig = BrowserWaitConfig.long()
    screenshot: bool | None = True
    empty_page_max_retry: int = 5
    chrome_args: list[str] | None = None

    def set_headless(self: Self, value: bool = True) -> Self:
        return self._copy_and_validate(headless=value)

    def set_proxy(self: Self, value: ProxySettings | None) -> Self:
        return self._copy_and_validate(proxy=value)

    def set_user_agent(self: Self, value: str | None) -> Self:
        return self._copy_and_validate(user_agent=value)

    def set_cdp_debug(self: Self, value: bool) -> Self:
        return self._copy_and_validate(cdp_debug=value)

    def set_cdp_url(self: Self, value: str) -> Self:
        return self._copy_and_validate(cdp_url=value)

    def set_web_security(self: Self, value: bool = True) -> Self:
        if value:
            return self._copy_and_validate(handler=self.handler.enable_web_security())
        else:
            return self._copy_and_validate(handler=self.handler.disable_web_security())

    def disable_web_security(self: Self) -> Self:
        return self.set_web_security(False)

    def enable_web_security(self: Self) -> Self:
        return self.set_web_security(True)

    def set_screenshot(self: Self, value: bool | None) -> Self:
        return self._copy_and_validate(screenshot=value)

    def set_empty_page_max_retry(self: Self, value: int) -> Self:
        return self._copy_and_validate(empty_page_max_retry=value)

    def set_wait(self: Self, value: BrowserWaitConfig) -> Self:
        return self._copy_and_validate(wait=value)

    def set_handler(self: Self, value: BrowserResourceHandlerConfig) -> Self:
        return self._copy_and_validate(handler=value)

    @override
    def set_verbose(self: Self) -> Self:
        return self.set_deep_verbose()

    def set_cookies_path(self: Self, value: str | None) -> Self:
        return self._copy_and_validate(cookies_path=value)

    def set_browser_type(self: Self, value: BrowserType) -> Self:
        return self._copy_and_validate(browser_type=value)

    @property
    def resource_options(self) -> BrowserResourceOptions:
        return BrowserResourceOptions(
            headless=self.headless,
            proxy=self.proxy,
            user_agent=self.user_agent,
            debug=self.cdp_debug,
            cdp_url=self.cdp_url,
            cookies=Cookie.from_json(self.cookies_path) if self.cookies_path is not None else None,
            browser_type=self.browser_type,
            chrome_args=self.chrome_args,
        )


class BrowserWindow(BaseModel):
    config: BrowserWindowConfig = Field(default_factory=BrowserWindowConfig)
    handler: PlaywrightResourceHandler | None = None
    resource: BrowserResource | None = None
    internal_handler: bool = False
    vault_replacement_fn: Callable[..., dict[str, str]] | None = None

    @override
    def model_post_init(cls, __context: Any) -> None:
        if cls.handler is None:
            cls.handler = BrowserResourceHandler(config=cls.config.handler)
            cls.internal_handler = True

    @property
    def browser_handler(self) -> PlaywrightResourceHandler:
        if self.handler is None:
            raise BrowserNotStartedError()
        return self.handler

    @property
    def page(self) -> Page:
        if self.resource is None:
            raise BrowserNotStartedError()
        return self.resource.page

    @property
    def port(self) -> int:
        if self.resource is None:
            raise BrowserNotStartedError()
        if self.resource.resource_options.debug_port is None:
            raise RemoteDebuggingNotAvailableError()
        return self.resource.resource_options.debug_port

    async def get_ws_url(self) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://localhost:{self.port}/json/version")
            data = response.json()
            return data["webSocketDebuggerUrl"]

    async def get_cdp_session(self, tab_idx: int | None = None) -> CDPSession:
        cdp_page = self.tabs[tab_idx] if tab_idx is not None else self.page
        return await cdp_page.context.new_cdp_session(cdp_page)

    async def page_id(self, tab_idx: int | None = None) -> str:
        session = await self.get_cdp_session(tab_idx)
        target_id: Any = await session.send("Target.getTargetInfo")  # pyright: ignore[reportUnknownMemberType]
        return target_id["targetInfo"]["targetId"]

    async def ws_page_url(self, tab_idx: int | None = None) -> str:
        page_id = await self.page_id(tab_idx)
        return f"ws://localhost:{self.port}/devtools/page/{page_id}"

    @page.setter
    def page(self, page: Page) -> None:
        if self.resource is None:
            raise BrowserNotStartedError()
        self.resource.page = page

    @property
    def tabs(self) -> list[Page]:
        return self.page.context.pages

    async def start(self) -> None:
        if self.resource is None:
            if self.internal_handler:
                await self.browser_handler.start()
            self.resource = await self.browser_handler.get_browser_resource(self.config.resource_options)
            # Create and track a new context
            self.resource.page.set_default_timeout(self.config.wait.step)

    async def close(self) -> None:
        if self.resource is not None:
            await self.browser_handler.release_browser_resource(self.resource)
            if self.internal_handler:
                await self.browser_handler.stop()
            self.resource = None

    async def long_wait(self) -> None:
        start_time = time.time()
        try:
            await self.page.wait_for_load_state("networkidle", timeout=self.config.wait.goto)
        except PlaywrightTimeoutError:
            if self.config.handler.verbose:
                logger.warning(f"Timeout while waiting for networkidle state for '{self.page.url}'")
        await self.short_wait()
        # await self.page.wait_for_timeout(self._playwright.config.step_timeout)
        if self.config.handler.verbose:
            logger.info(f"Waited for networkidle state for '{self.page.url}' in {time.time() - start_time:.2f}s")

    async def short_wait(self) -> None:
        await self.page.wait_for_timeout(self.config.wait.short_wait)

    async def tab_metadata(self, tab_idx: int | None = None) -> TabsData:
        page = self.tabs[tab_idx] if tab_idx is not None else self.page
        return TabsData(
            tab_id=tab_idx if tab_idx is not None else -1,
            title=await page.title(),
            url=page.url,
        )

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
            tabs=[await self.tab_metadata(i) for i, _ in enumerate(self.tabs)],
        )

    async def collect_hidden_locators(self) -> list[Locator]:
        hidden_values: set[str]
        if self.vault_replacement_fn is None:
            hidden_values = set()
        else:
            hidden_values = set(self.vault_replacement_fn().keys())

        hidden_locators: list[Locator] = []
        if len(hidden_values) > 0:
            # might be able to evaluate all locators, at once
            # fine for now
            for input_el in await self.page.locator("input").all():
                input_val = await input_el.evaluate("el => el.value")

                if input_val in hidden_values:
                    hidden_locators.append(input_el)
        return hidden_locators

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

        except SnapshotProcessingError:
            await self.long_wait()
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)

        except Exception as e:
            if "has been closed" in str(e):
                raise BrowserExpiredError() from e
            if "Unable to retrieve content because the page is navigating and changing the content" in str(e):
                # Should retry after the page is loaded
                await self.short_wait()
            else:
                raise UnexpectedBrowserError(url=self.page.url) from e

        a11y_tree = None
        if a11y_simple is None or a11y_raw is None or len(a11y_simple.get("children", [])) == 0:
            logger.warning("A11y tree is empty, this might cause unforeseen issues")

        else:
            a11y_tree = A11yTree(
                simple=a11y_simple,
                raw=a11y_raw,
            )

        if dom_node is None:
            if self.config.handler.verbose:
                logger.warning(f"Empty page content for {self.page.url}. Retry in {self.config.wait.short_wait}ms")
            await self.page.wait_for_timeout(self.config.wait.short_wait)
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)
        take_screenshot = screenshot if screenshot is not None else self.config.screenshot
        try:
            snapshot_screenshot = (
                await self.page.screenshot(mask=await self.collect_hidden_locators()) if take_screenshot else None
            )
        except PlaywrightTimeoutError:
            if self.config.handler.verbose:
                logger.warning(f"Timeout while taking screenshot for {self.page.url}. Retrying...")
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)

        return BrowserSnapshot(
            metadata=await self.snapshot_metadata(),
            html_content=html_content,
            a11y_tree=a11y_tree,
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
