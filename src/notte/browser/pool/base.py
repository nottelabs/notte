import asyncio
import datetime as dt
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from loguru import logger
from patchright.async_api import (
    Browser as PlaywrightBrowser,
)
from patchright.async_api import (
    BrowserContext as PlaywrightBrowserContext,
)
from patchright.async_api import (
    Page as PlaywrightPage,
)
from patchright.async_api import (
    Playwright,
    async_playwright,
)

from notte.errors.browser import BrowserNotStartedError, BrowserResourceNotFoundError


@dataclass
class BrowserResource:
    page: PlaywrightPage
    browser_id: str
    context_id: str
    headless: bool


@dataclass
class TimeContext:
    context_id: str
    context: PlaywrightBrowserContext
    timestamp: dt.datetime = field(default_factory=lambda: dt.datetime.now())


@dataclass
class BrowserWithContexts:
    browser_id: str
    browser: PlaywrightBrowser
    contexts: dict[str, TimeContext]
    headless: bool
    timestamp: dt.datetime = field(default_factory=lambda: dt.datetime.now())
    cdp_url: str | None = None


class BaseBrowserPool(ABC):
    BROWSER_CREATION_TIMEOUT_SECONDS: ClassVar[int] = 30
    BROWSER_OPERATION_TIMEOUT_SECONDS: ClassVar[int] = 30

    def __init__(
        self,
        contexts_per_browser: int = 4,
        viewport_width: int = 1280,
        viewport_height: int = 1020,
        verbose: bool = False,
    ) -> None:
        self._playwright: Playwright | None = None
        self._browsers: dict[str, BrowserWithContexts] = {}
        self._headless_browsers: dict[str, BrowserWithContexts] = {}
        self._contexts_per_browser: int = contexts_per_browser
        self.verbose: int = verbose
        self.viewport_width: int = viewport_width
        self.viewport_height: int = viewport_height

    def available_browsers(self, headless: bool | None = None) -> dict[str, BrowserWithContexts]:
        if headless is None:
            return {**self._headless_browsers, **self._browsers}
        elif headless:
            return self._headless_browsers
        else:
            return self._browsers

    async def start(self) -> None:
        """Initialize the playwright instance"""
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def stop(self) -> None:
        """Stop the playwright instance"""
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
            self._browsers = {}
            self._headless_browsers = {}

    @property
    def playwright(self) -> Playwright:
        if self._playwright is None:
            raise BrowserNotStartedError()
        return self._playwright

    @abstractmethod
    async def create_playwright_browser(self, headless: bool) -> PlaywrightBrowser:
        pass

    @abstractmethod
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        pass

    async def create_browser(self, headless: bool) -> BrowserWithContexts:
        """Get an existing browser or create a new one if needed"""

        browser = await self.create_playwright_browser(headless)
        browser_id = str(uuid.uuid4())
        _browser = BrowserWithContexts(
            browser_id=browser_id,
            browser=browser,
            contexts={},
            headless=headless,
        )
        # Store browser reference
        self.available_browsers(headless)[browser_id] = _browser
        return _browser

    async def get_or_create_browser(self, headless: bool) -> BrowserWithContexts:
        """Find a browser with available space for a new context"""
        browsers = self.available_browsers(headless)
        for browser in browsers.values():
            if len(browser.contexts) < self._contexts_per_browser:
                return browser
        # Create a new browser
        if self.verbose:
            logger.info(f"Maximum contexts per browser reached ({self._contexts_per_browser}). Creating new browser...")
        browser = await self.create_browser(headless)
        return browser

    def create_context(self, browser: BrowserWithContexts, context: PlaywrightBrowserContext) -> str:
        context_id = str(uuid.uuid4())
        browser.contexts[context_id] = TimeContext(context_id=context_id, context=context)
        return context_id

    async def get_browser_resource(
        self,
        headless: bool,
    ) -> BrowserResource:
        browser = await self.get_or_create_browser(headless)

        try:
            async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                context = await browser.browser.new_context(
                    no_viewport=False,
                    viewport={
                        "width": self.viewport_width,
                        "height": self.viewport_height,
                    },
                )
                context_id = self.create_context(browser, context)
                if len(context.pages) == 0:
                    page = await context.new_page()
                else:
                    page = context.pages[-1]
                return BrowserResource(
                    page=page, context_id=context_id, browser_id=browser.browser_id, headless=browser.headless
                )
        except Exception as e:
            logger.error(f"Failed to create browser resource: {e}")
            # Cleanup on failure
            for context_id, context in browser.contexts.items():
                try:
                    await context.context.close()
                    del browser.contexts[context_id]
                except Exception:
                    pass
            raise

    async def release_browser_resource(self, resource: BrowserResource) -> None:
        browsers = self.available_browsers(resource.headless)
        if resource.browser_id not in browsers:
            raise BrowserResourceNotFoundError(
                f"Browser '{resource.browser_id}' not found in available browsers (i.e {list(browsers.keys())})"
            )
        resource_browser = browsers[resource.browser_id]
        if resource.context_id not in resource_browser.contexts:
            raise BrowserResourceNotFoundError(
                (
                    f"Context '{resource.context_id}' not found in available "
                    f"contexts (i.e {list(resource_browser.contexts.keys())})"
                )
            )
        try:
            async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                await resource_browser.contexts[resource.context_id].context.close()
        except Exception as e:
            logger.error(f"Failed to close snapshot: {e}")
            return
        del resource_browser.contexts[resource.context_id]
        if len(resource_browser.contexts) == 0:
            if self.verbose:
                logger.info(f"Closing browser {resource.browser_id}")
            status = await self.close_playwright_browser(resource_browser)
            if status:
                del browsers[resource.browser_id]
