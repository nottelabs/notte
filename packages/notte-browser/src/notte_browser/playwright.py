import asyncio
from abc import ABC, abstractmethod
from typing import ClassVar

from loguru import logger
from notte_core.common.config import BrowserType
from notte_core.common.resource import AsyncResource
from notte_core.profiling import profiler
from notte_sdk.types import SessionStartRequest
from openai import BaseModel
from patchright.async_api import (
    Browser as PlaywrightBrowser,
)
from patchright.async_api import (
    BrowserContext,
    Playwright,
    async_playwright,
)
from pydantic import PrivateAttr
from typing_extensions import override

from notte_browser.errors import BrowserNotStartedError, CdpConnectionError, FirefoxNotAvailableError
from notte_browser.window import BrowserResource, BrowserWindow, BrowserWindowOptions


class BaseWindowManager(AsyncResource, ABC):
    @abstractmethod
    async def new_window(self, options: BrowserWindowOptions) -> BrowserWindow:
        pass


class PlaywrightManager(BaseModel, BaseWindowManager):
    model_config = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "arbitrary_types_allowed": True
    }
    BROWSER_CREATION_TIMEOUT_SECONDS: ClassVar[int] = 30
    BROWSER_OPERATION_TIMEOUT_SECONDS: ClassVar[int] = 30
    verbose: bool = False
    _playwright: Playwright | None = PrivateAttr(default=None)

    @override
    async def astart(self) -> None:
        """Initialize the playwright instance"""
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    @override
    async def astop(self) -> None:
        """Stop the playwright instance"""
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def is_started(self) -> bool:
        return self._playwright is not None

    @property
    def playwright(self) -> Playwright:
        if self._playwright is None:
            raise BrowserNotStartedError()
        return self._playwright

    def set_playwright(self, playwright: Playwright) -> None:
        self._playwright = playwright

    async def connect_cdp_browser(self, options: BrowserWindowOptions) -> PlaywrightBrowser:
        if options.cdp_url is None:
            raise ValueError("CDP URL is required to connect to a browser over CDP")
        try:
            match options.browser_type:
                case BrowserType.CHROMIUM | BrowserType.CHROME:
                    return await self.playwright.chromium.connect_over_cdp(options.cdp_url)
                case BrowserType.FIREFOX:
                    return await self.playwright.firefox.connect(options.cdp_url)
        except Exception as e:
            raise CdpConnectionError(options.cdp_url) from e

    async def create_playwright_browser(self, options: BrowserWindowOptions) -> PlaywrightBrowser:
        """Get an existing browser or create a new one if needed"""
        if options.cdp_url is not None:
            return await self.connect_cdp_browser(options)

        if self.verbose:
            if options.debug_port is not None:
                logger.info(f"🪟 [Browser Settings] Launching browser in debug mode on port {options.debug_port}")
            if options.cdp_url is not None:
                logger.info(f"🪟 [Browser Settings] Connecting to browser over CDP at {options.cdp_url}")
            if options.proxy is not None:
                logger.info(f"🪟 [Browser Settings] Using proxy {options.proxy.get('server', 'unknown')}")
            if options.browser_type == BrowserType.FIREFOX:
                logger.info(
                    f"🪟 [Browser Settings] Using {options.browser_type} browser. Note that CDP may not be supported for this browser."
                )

        match options.browser_type:
            case BrowserType.CHROMIUM | BrowserType.CHROME:
                if options.headless and options.user_agent is None:
                    logger.warning(
                        "🪟 [Browser Settings] Launching browser in headless without providing a user-agent"
                        + ", for better odds at evading bot detection, set a user-agent or run in headful mode"
                    )
                browser = await self.playwright.chromium.launch(
                    channel="chrome" if options.browser_type == BrowserType.CHROME else None,
                    headless=options.headless,
                    proxy=options.proxy,
                    timeout=self.BROWSER_CREATION_TIMEOUT_SECONDS * 1000,
                    args=options.get_chrome_args(),
                )
            case BrowserType.FIREFOX:
                # TODO: add firefox support: this is not currently supported by patchright
                # browser = await self.playwright.firefox.launch(
                #     headless=options.headless,
                #     proxy=options.proxy,
                #     timeout=self.BROWSER_CREATION_TIMEOUT_SECONDS * 1000,
                # )
                raise FirefoxNotAvailableError()
        return browser

    async def get_browser_resource(self, options: BrowserWindowOptions, browser: PlaywrightBrowser) -> BrowserResource:
        async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
            viewport = None
            if options.viewport_width is not None or options.viewport_height is not None:
                viewport = {
                    "width": options.viewport_width,
                    "height": options.viewport_height,
                }
            else:
                logger.warning(
                    f"🪟 No viewport set in {'headless' if options.headless else 'headful'} mode, using default viewport in playwright"
                )

            context: BrowserContext = await browser.new_context(
                # no viewport should be False for headless browsers
                no_viewport=not options.headless,
                viewport=viewport,  # pyright: ignore[reportArgumentType]
                permissions=[
                    # Needed for clipboard copy/paste to respect tabs / new lines for chromium browsers
                    "clipboard-read",
                    "clipboard-write",
                ]
                if options.browser_type in [BrowserType.CHROMIUM, BrowserType.CHROME]
                else [],
                proxy=options.proxy,
                user_agent=options.user_agent,
            )

            if len(context.pages) == 0:
                page = await context.new_page()
            else:
                page = context.pages[-1]
            return BrowserResource(
                page=page,
                options=options,
            )

    @override
    async def new_window(self, options: BrowserWindowOptions | None = None) -> BrowserWindow:
        if not self.is_started():
            _ = await self.astart()
        options = options or BrowserWindowOptions.from_request(SessionStartRequest())
        browser = await self.create_playwright_browser(options)
        resource = await self.get_browser_resource(options, browser)

        async def on_close() -> None:
            try:
                async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                    await browser.close()
                    await self.astop()
            except Exception as e:
                logger.error(f"Failed to close window: {e}")

        return BrowserWindow(
            resource=resource,
            on_close=on_close,
        )
