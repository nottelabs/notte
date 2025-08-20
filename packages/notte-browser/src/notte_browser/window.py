import asyncio
import os
import random
import time
from collections.abc import Awaitable
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, ClassVar, Literal, Self

import httpx
from loguru import logger
from notte_core.browser.dom_tree import A11yNode, A11yTree, DomNode
from notte_core.browser.snapshot import (
    BrowserSnapshot,
    SnapshotMetadata,
    TabsData,
    ViewportData,
)
from notte_core.common.config import BrowserType, PlaywrightProxySettings, config
from notte_core.errors.processing import SnapshotProcessingError
from notte_core.profiling import profiler
from notte_core.utils.url import is_valid_url
from notte_sdk.types import (
    DEFAULT_HEADLESS_VIEWPORT_HEIGHT,
    DEFAULT_HEADLESS_VIEWPORT_WIDTH,
    Cookie,
    CookieDict,
    SessionStartRequest,
)
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from notte_browser.dom.parsing import dom_tree_parsers
from notte_browser.errors import (
    BrowserExpiredError,
    EmptyPageContentError,
    InvalidProxyError,
    InvalidURLError,
    PageLoadingError,
    PlaywrightError,
    PlaywrightTimeoutError,
    RemoteDebuggingNotAvailableError,
    UnexpectedBrowserError,
)
from notte_browser.playwright_async_api import CDPSession, Locator, Page, Response


class BrowserWindowOptions(BaseModel):
    headless: bool
    solve_captchas: bool
    user_agent: str | None
    proxy: PlaywrightProxySettings | None
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
        self.cdp_url = cdp_url
        return self

    @override
    def model_post_init(self, __context: Any) -> None:
        if self.headless and self.viewport_width is None and self.viewport_height is None:
            width_variation = random.randint(-50, 50)
            height_variation = random.randint(-50, 50)
            logger.warning(
                f"🪟 Headless mode detected. Setting default viewport width and height to {DEFAULT_HEADLESS_VIEWPORT_WIDTH}x{DEFAULT_HEADLESS_VIEWPORT_HEIGHT} to avoid issues."
            )
            self.viewport_width = DEFAULT_HEADLESS_VIEWPORT_WIDTH + width_variation
            self.viewport_height = DEFAULT_HEADLESS_VIEWPORT_HEIGHT + height_variation

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
        if os.getenv("DISABLE_GPU") is not None:
            logger.warning(
                "🪟 Disabling GPU in chrome args. You can remove the DISABLE_GPU environment variable to enable it."
            )
            chrome_args.extend(["--disable-gpu"])
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
    def from_request(request: SessionStartRequest) -> "BrowserWindowOptions":
        return BrowserWindowOptions(
            headless=request.headless,
            solve_captchas=request.solve_captchas,
            user_agent=request.user_agent,
            proxy=request.playwright_proxy,
            browser_type=request.browser_type,
            chrome_args=request.chrome_args,
            viewport_height=request.viewport_height,
            viewport_width=request.viewport_width,
            cdp_url=request.cdp_url,
            web_security=config.web_security,
            debug_port=config.debug_port,
            custom_devtools_frontend=config.custom_devtools_frontend,
        )


class BrowserResource(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)

    page: Page = Field(exclude=True)
    options: BrowserWindowOptions
    browser_id: str | None = None
    context_id: str | None = None


class ScreenshotMask(BaseModel):
    async def mask(self, page: Page) -> list[Locator]:  # pyright: ignore[reportUnusedParameter]
        return []


class BrowserWindow(BaseModel):
    resource: BrowserResource
    screenshot_mask: ScreenshotMask | None = None
    on_close: Callable[[], Awaitable[None]] | None = None
    page_callbacks: dict[str, Callable[[Page], None]] = Field(default_factory=dict)
    goto_response: Response | None = Field(exclude=True, default=None)

    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)

    @override
    def model_post_init(self, __context: Any) -> None:
        self.resource.page.set_default_timeout(config.timeout_default_ms)
        self.apply_page_callbacks()

    def apply_page_callbacks(self):
        for key, callback in self.page_callbacks.items():
            self.page.on(key, callback)  # pyright: ignore [reportArgumentType, reportCallIssue]

    @property
    def page(self) -> Page:
        return self.resource.page

    async def close(self) -> None:
        if self.on_close is not None:
            await self.on_close()
        for tab in self.tabs:
            await tab.close()

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
        self.apply_page_callbacks()

    @property
    def tabs(self) -> list[Page]:
        return self.page.context.pages

    @profiler.profiled()
    async def long_wait(self) -> None:
        start_time = time.time()
        try:
            await self.page.wait_for_load_state("networkidle", timeout=config.timeout_goto_ms)
        except PlaywrightTimeoutError:
            if config.verbose:
                logger.warning(f"Timeout while waiting for networkidle state for '{self.page.url}'")
        await self.short_wait()
        # await self.page.wait_for_timeout(self._playwright.config.step_timeout)
        if config.verbose:
            logger.trace(f"Waited for networkidle state for '{self.page.url}' in {time.time() - start_time:.2f}s")

    @profiler.profiled()
    async def short_wait(self) -> None:
        await self.page.wait_for_timeout(config.wait_short_ms)

    async def tab_metadata(self, tab_idx: int | None = None) -> TabsData:
        page = self.tabs[tab_idx] if tab_idx is not None else self.page
        return TabsData(
            tab_id=tab_idx if tab_idx is not None else -1,
            title=await page.title(),
            url=page.url,
        )

    @profiler.profiled()
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

    @profiler.profiled()
    async def screenshot(self, retries: int = config.empty_page_max_retry) -> bytes:
        if retries <= 0:
            raise EmptyPageContentError(url=self.page.url, nb_retries=config.empty_page_max_retry)
        try:
            mask = await self.screenshot_mask.mask(self.page) if self.screenshot_mask is not None else None
            return await self.page.screenshot(mask=mask)
        except PlaywrightTimeoutError:
            if config.verbose:
                logger.debug(f"Timeout while taking screenshot for {self.page.url}. Retrying...")
            await self.short_wait()
            return await self.screenshot(retries=retries - 1)

    async def a11y(self) -> A11yTree | None:
        a11y_simple: A11yNode | None = await profiler.profiled()(self.page.accessibility.snapshot)()  # type: ignore[attr-defined]
        a11y_raw: A11yNode | None = await profiler.profiled()(self.page.accessibility.snapshot)(interesting_only=False)  # type: ignore[attr-defined]
        if a11y_simple is None or a11y_raw is None or len(a11y_simple.get("children", [])) == 0:
            logger.warning("A11y tree is empty, this might cause unforeseen issues")
            return None
        return A11yTree(
            simple=a11y_simple,
            raw=a11y_raw,
        )

    @profiler.profiled()
    async def snapshot(
        self, screenshot: bool | None = None, retries: int = config.empty_page_max_retry
    ) -> BrowserSnapshot:
        if retries <= 0:
            raise EmptyPageContentError(url=self.page.url, nb_retries=config.empty_page_max_retry)
        html_content: str = ""
        dom_node: DomNode | None = None
        snapshot_screenshot = None
        try:
            html_content = await profiler.profiled()(self.page.content)()
            dom_tree_pipe = dom_tree_parsers["default"]
            snapshot_screenshot, dom_node = await asyncio.gather(self.screenshot(), dom_tree_pipe.forward(self.page))

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

        if dom_node is None or snapshot_screenshot is None:
            if config.verbose:
                logger.warning(f"Empty page content for {self.page.url}. Retry in {config.wait_retry_snapshot_ms}ms")
            await self.page.wait_for_timeout(config.wait_retry_snapshot_ms)
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)

        try:
            snapshot_metadata = await self.snapshot_metadata()

            return BrowserSnapshot(
                metadata=snapshot_metadata,
                html_content=html_content,
                a11y_tree=None,
                dom_node=dom_node,
                screenshot=snapshot_screenshot,
            )
        except PlaywrightError:
            return await self.snapshot(screenshot=screenshot, retries=retries - 1)

    async def goto_and_wait(
        self, url: str | None = None, tries: int = 3, operation: Literal["back", "forward"] | None = None
    ) -> None:
        def is_default_page():
            return self.page.url == "about:blank" and not url == "about:blank"

        def on_response(resp: Response) -> None:
            """Store the response so its available for exception handling."""
            self.goto_response = resp

        while True:
            self.goto_response = None
            self.page.once("response", on_response)
            tries -= 1

            try:
                match operation:
                    case None:
                        assert url is not None, "URL is required for goto"
                        _ = await self.page.goto(url, timeout=config.timeout_goto_ms)
                    case "back":
                        _ = await self.page.go_back(timeout=config.timeout_goto_ms)
                    case "forward":
                        _ = await self.page.go_forward(timeout=config.timeout_goto_ms)
                if self.goto_response is not None:
                    logger.info(
                        f"Goto for {url=} succeeded with HTTP {self.goto_response.status}: {self.goto_response.status_text}"
                    )
            except PlaywrightTimeoutError:
                await self.long_wait()
            except Exception as e:
                if self.goto_response is not None:
                    if self.goto_response.status == HTTPStatus.PROXY_AUTHENTICATION_REQUIRED:
                        raise InvalidProxyError(url=url or self.page.url)
                    logger.warning(
                        f"Goto for {url=} failed with HTTP {self.goto_response.status}: {self.goto_response.status_text}"
                    )
                raise PageLoadingError(url=url or self.page.url) from e

            # extra wait to make sure that css animations can start
            # to make extra element visible
            await self.short_wait()

            if not is_default_page() or tries < 0:
                break

        if is_default_page():
            raise PageLoadingError(url=url or self.page.url)

    async def goto(self, url: str, tries: int = 3) -> None:
        if url == self.page.url:
            return
        prefixes = ("http://", "https://")

        if not any(url.startswith(prefix) for prefix in prefixes):
            logger.info(f"Provided URL doesnt have a scheme, adding https to {url}")
            url = "https://" + url

        if not is_valid_url(url, check_reachability=False):
            raise InvalidURLError(url=url)

        await self.goto_and_wait(url=url, tries=tries, operation=None)

    async def set_cookies(self, cookies: list[CookieDict] | None = None, cookie_path: str | Path | None = None) -> None:
        if cookies is None and cookie_path is not None:
            _cookies = Cookie.from_json(cookie_path)
            cookies = [cookie.model_dump() for cookie in _cookies]  # type: ignore
        if cookies is None:
            raise ValueError("No cookies provided")

        if config.verbose:
            logger.info("🍪 Adding cookies to browser...")
        await self.page.context.add_cookies(cookies)  # type: ignore

    async def get_cookies(self) -> list[CookieDict]:
        def format_cookie(data: dict[str, Any]) -> CookieDict:
            cookie = Cookie.model_validate(data)
            return CookieDict(
                name=cookie.name,
                domain=cookie.domain,
                path=cookie.path,
                httpOnly=cookie.httpOnly,
                expirationDate=cookie.expirationDate,
                hostOnly=cookie.hostOnly,
                sameSite=cookie.sameSite,
                secure=cookie.secure,
                session=cookie.session,
                storeId=cookie.storeId,
                value=cookie.value,
                expires=cookie.expires,
            )

        return [format_cookie(cookie) for cookie in await self.page.context.cookies()]  # type: ignore
