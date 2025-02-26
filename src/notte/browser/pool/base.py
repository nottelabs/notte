from abc import ABC, abstractmethod
import asyncio
import datetime as dt
import uuid
from abc import ABC, abstractmethod
from typing import ClassVar
import os

from loguru import logger
from openai import BaseModel
from patchright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from pydantic import Field, PrivateAttr

from notte.browser.pool.ports import get_port_manager
from notte.common.config import FrozenConfig
from notte.errors.browser import BrowserPoolNotStartedError, BrowserResourceNotFoundError


class BrowserResource(BaseModel):
    model_config = {"arbitrary_types_allowed": True}  # pyright: ignore[reportUnannotatedClassAttribute]

    page: PlaywrightPage = Field(exclude=True)
    browser_id: str
    context_id: str
    headless: bool
    port: int | None = None


class TimeContext(BaseModel):
    model_config = {"arbitrary_types_allowed": True}  # pyright: ignore[reportUnannotatedClassAttribute]
    context_id: str
    context: PlaywrightBrowserContext = Field(exclude=True)
    timestamp: dt.datetime = Field(default_factory=lambda: dt.datetime.now())


class BrowserWithContexts(BaseModel):
    model_config = {"arbitrary_types_allowed": True}  # pyright: ignore[reportUnannotatedClassAttribute]

    browser_id: str
    browser: PlaywrightBrowser = Field(exclude=True)
    contexts: dict[str, TimeContext]
    headless: bool
    timestamp: dt.datetime = Field(default_factory=lambda: dt.datetime.now())
    port: int | None = None
    cdp_url: str | None = None


class BaseBrowserPoolConfig(FrozenConfig):
    contexts_per_browser: int = 4
    viewport_width: int = 1280
    viewport_height: int = 1020
    verbose: bool = False


class BaseBrowserPool(ABC, BaseModel):
    BROWSER_CREATION_TIMEOUT_SECONDS: ClassVar[int] = 30
    BROWSER_OPERATION_TIMEOUT_SECONDS: ClassVar[int] = 30

    config: BaseBrowserPoolConfig = BaseBrowserPoolConfig()
    _playwright: Playwright | None = PrivateAttr(default=None)
    browsers: dict[str, BrowserWithContexts] = Field(default_factory=dict)
    headless_browsers: dict[str, BrowserWithContexts] = Field(default_factory=dict)

    def available_browsers(self, headless: bool | None = None) -> dict[str, BrowserWithContexts]:
        if headless is None:
            return {**self.headless_browsers, **self.browsers}
        elif headless:
            return self.headless_browsers
        else:
            return self.browsers

    async def start(self) -> None:
        """Initialize the playwright instance"""
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def stop(self) -> None:
        """Stop the playwright instance"""
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
            self.browsers = {}
            self.headless_browsers = {}

    @property
    def playwright(self) -> Playwright:
        if self._playwright is None:
            raise BrowserPoolNotStartedError()
        return self._playwright

    @abstractmethod
    async def create_playwright_browser(self, headless: bool, port: int | None) -> PlaywrightBrowser:
        pass

    @abstractmethod
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        pass

    async def create_browser(self, headless: bool) -> BrowserWithContexts:
        """Get an existing browser or create a new one if needed"""
        port_manager = get_port_manager()
        port = None if port_manager is None else port_manager.acquire_port()
        browser = await self.create_playwright_browser(headless, port=port)
        browser_id = str(uuid.uuid4())
        _browser = BrowserWithContexts(
            browser_id=browser_id,
            browser=browser,
            contexts={},
            headless=headless,
            port=port,
        )
        # Store browser reference
        self.available_browsers(headless)[browser_id] = _browser
        return _browser

    async def get_or_create_browser(self, headless: bool) -> BrowserWithContexts:
        """Find a browser with available space for a new context"""
        browsers = self.available_browsers(headless)
        for browser in browsers.values():
            if len(browser.contexts) < self.config.contexts_per_browser:
                return browser
        # Create a new browser
        if self.config.verbose:
            logger.info(
                f"Maximum contexts per browser reached ({self.config.contexts_per_browser}). Creating new browser..."
            )
        browser = await self.create_browser(headless)
        return browser

    def create_context(self, browser: BrowserWithContexts, context: BrowserContext) -> str:
        context_id = str(uuid.uuid4())
        browser.contexts[context_id] = TimeContext(context_id=context_id, context=context)
        return context_id

    async def get_browser_resource(
        self,
        headless: bool,
        width: int | None = None,
        height: int | None = None,
    ) -> BrowserResource:
        browser = await self.get_or_create_browser(headless)

        try:
            async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                context = await browser.browser.new_context(
                    no_viewport=False,
                    viewport={
                        "width": self.config.viewport_width,
                        "height": self.config.viewport_height,
                    },
                    permissions=[
                        "clipboard-read",
                        "clipboard-write",
                    ],  # Needed for clipboard copy/paste to respect tabs / new lines
                )
                context_id = self.create_context(browser, context)
                if len(context.pages) == 0:
                    page = await context.new_page()
                else:
                    page = context.pages[-1]
                return BrowserResource(
                    page=page,
                    context_id=context_id,
                    browser_id=browser.browser_id,
                    headless=browser.headless,
                    port=browser.port,
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

    async def release_browser(self, browser: BrowserWithContexts) -> None:
        if self.config.verbose:
            logger.info(f"Releasing browser {browser.browser_id}...")
        browsers = self.available_browsers(headless=browser.headless)
        if browser.browser_id not in browsers:
            raise BrowserResourceNotFoundError(
                f"Browser '{browser.browser_id}' not found in available browsers (i.e {list(browsers.keys())})"
            )
        status = await self.close_playwright_browser(browser)
        if not status:
            logger.error(f"/!\\ VERY BAD THING HAPPENED: Failed to close browser {browser.browser_id}")
        port_manager = get_port_manager()
        if port_manager is not None and browser.port is not None:
            port_manager.release_port(browser.port)
        del browsers[browser.browser_id]

    async def release_browser_resource(self, resource: BrowserResource) -> None:
        browsers = self.available_browsers(resource.headless)
        if resource.browser_id not in browsers:
            raise BrowserResourceNotFoundError(
                f"Browser '{resource.browser_id}' not found in available browsers (i.e {list(browsers.keys())})"
            )
        resource_browser = browsers[resource.browser_id]
        if resource.context_id not in resource_browser.contexts:
            raise BrowserResourceNotFoundError(
                f"Context '{resource.context_id}' not found in available "
                f"contexts (i.e {list(resource_browser.contexts.keys())})"
            )
        try:
            async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                await resource_browser.contexts[resource.context_id].context.close()
        except Exception as e:
            logger.error(f"Failed to close context: {e}")
            return
        del resource_browser.contexts[resource.context_id]
        if len(resource_browser.contexts) == 0:
            await self.release_browser(resource_browser)
