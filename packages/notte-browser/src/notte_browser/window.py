import time
from collections.abc import Awaitable
from pathlib import Path
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
from notte_core.common.config import BrowserType, FrozenConfig, config
from notte_core.errors.processing import SnapshotProcessingError
from notte_core.utils.url import is_valid_url
from notte_sdk.types import Cookie, ProxySettings, SessionStartRequest
from patchright.async_api import CDPSession, Locator, Page
from patchright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, Field
from typing_extensions import override

from notte_browser.dom.parsing import ParseDomTreePipe
from notte_browser.errors import (
    BrowserExpiredError,
    EmptyPageContentError,
    InvalidURLError,
    PageLoadingError,
    RemoteDebuggingNotAvailableError,
    UnexpectedBrowserError,
)


class BrowserWindowOptions(FrozenConfig):
    headless: bool
    user_agent: str | None
    proxy: ProxySettings | None
    viewport_width: int | None
    viewport_height: int | None
    browser_type: BrowserType
    chrome_args: list[str] | None
    web_security: bool

    # Debugging args
    cdp_url: str | None
    debug_port: int | None
    custom_devtools_frontend: str | None

    def set_cdp_url(self, cdp_url: str) -> Self:
        return self._copy_and_validate(cdp_url=cdp_url)

    def get_chrome_args(self) -> list[str]:
        chrome_args = self.chrome_args or []
        if self.chrome_args is None:
            chrome_args.extend(
                [
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--no-zygote",
                    "--mute-audio",
                    '--js-flags="--max-old-space-size=100"',
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--start-maximized",
                ]
            )
        if len(chrome_args) == 0:
            logger.warning("Chrome args are empty. This is not recommended in production environments.")
        if not self.web_security:
            chrome_args.extend(
                [
                    "--disable-web-security",
                    "--disable-site-isolation-trials",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--remote-allow-origins=*",
                ]
            )

        if self.custom_devtools_frontend is not None:
            chrome_args.extend(
                [
                    f"--custom-devtools-frontend={self.custom_devtools_frontend}",
                ]
            )
        if self.debug_port is not None:
            chrome_args.append(f"--remote-debugging-port={self.debug_port}")
        return chrome_args

    @staticmethod
    def from_request(
        request: SessionStartRequest, headless: bool = True, user_agent: str | None = None
    ) -> "BrowserWindowOptions":
        return BrowserWindowOptions(
            headless=headless,
            user_agent=user_agent,
            proxy=request.load_proxy_settings(),
            browser_type=request.browser_type,
            chrome_args=request.chrome_args,
            viewport_height=request.viewport_height,
            viewport_width=request.viewport_width,
            web_security=config.web_security,
            cdp_url=config.cdp_url,
            debug_port=config.debug_port,
            custom_devtools_frontend=config.custom_devtools_frontend,
        )


class BrowserResource(BaseModel):
    model_config = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "arbitrary_types_allowed": True
    }

    page: Page = Field(exclude=True)
    options: BrowserWindowOptions
    browser_id: str | None = None
    context_id: str | None = None


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
    wait: BrowserWaitConfig = BrowserWaitConfig.long()
    screenshot: bool | None = True
    empty_page_max_retry: int = 5

    def set_wait(self: Self, value: BrowserWaitConfig) -> Self:
        return self._copy_and_validate(wait=value)


class ScreenshotMask(BaseModel):
    async def mask(self, page: Page) -> list[Locator]:  # pyright: ignore[reportUnusedParameter]
        return []


class BrowserWindow(BaseModel):
    config: BrowserWindowConfig = Field(default_factory=BrowserWindowConfig)
    resource: BrowserResource
    screenshot_mask: ScreenshotMask | None = None
    on_close: Callable[[], Awaitable[None]] | None = None

    @override
    def model_post_init(self, __context: Any) -> None:
        self.resource.page.set_default_timeout(self.config.wait.step)

    @property
    def page(self) -> Page:
        return self.resource.page

    async def close(self) -> None:
        if self.on_close is not None:
            await self.on_close()
        await self.resource.page.close()

    @property
    def port(self) -> int:
        if self.resource.options.debug_port is None:
            raise RemoteDebuggingNotAvailableError()
        return self.resource.options.debug_port

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
        self.resource.page = page

    @property
    def tabs(self) -> list[Page]:
        return self.page.context.pages

    async def long_wait(self) -> None:
        start_time = time.time()
        try:
            await self.page.wait_for_load_state("networkidle", timeout=self.config.wait.goto)
        except PlaywrightTimeoutError:
            if self.config.verbose:
                logger.warning(f"Timeout while waiting for networkidle state for '{self.page.url}'")
        await self.short_wait()
        # await self.page.wait_for_timeout(self._playwright.config.step_timeout)
        if self.config.verbose:
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
            if self.config.verbose:
                logger.warning(f"Empty page content for {self.page.url}. Retry in {self.config.wait.short_wait}ms")
            await self.page.wait_for_timeout(self.config.wait.short_wait)
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)
        take_screenshot = screenshot if screenshot is not None else self.config.screenshot
        try:
            mask = await self.screenshot_mask.mask(self.page) if self.screenshot_mask is not None else None
            snapshot_screenshot = await self.page.screenshot(mask=mask) if take_screenshot else None
        except PlaywrightTimeoutError:
            if self.config.verbose:
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

    async def set_cookies(self, cookies: list[Cookie] | None = None, cookie_path: str | Path | None = None) -> None:
        if cookies is None and cookie_path is not None:
            cookies = Cookie.from_json(cookie_path)
        if cookies is None:
            raise ValueError("No cookies provided")

        if self.config.verbose:
            logger.info("Adding cookies to browser...")
        await self.page.context.add_cookies([cookie.model_dump(exclude_none=True) for cookie in cookies])  # type: ignore

    async def get_cookies(self) -> list[Cookie]:
        return [Cookie.model_validate(cookie) for cookie in await self.page.context.cookies()]
