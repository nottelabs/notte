import asyncio
import datetime as dt
import uuid
from abc import ABC, abstractmethod
from typing import ClassVar

from loguru import logger
from notte_browser.errors import (
    BrowserPoolNotStartedError,
    BrowserResourceNotFoundError,
)
from notte_browser.resource import BrowserResource, BrowserResourceOptions, PlaywrightResourceHandler
from notte_core.common.config import FrozenConfig
from openai import BaseModel
from patchright.async_api import (
    Browser as PlaywrightBrowser,
)
from patchright.async_api import (
    BrowserContext as PlaywrightBrowserContext,
)
from pydantic import Field
from typing_extensions import override

from notte_pools.ports import get_port_manager


class TimeContext(BaseModel):
    model_config = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "arbitrary_types_allowed": True
    }
    context_id: str
    context: PlaywrightBrowserContext = Field(exclude=True)
    timestamp: dt.datetime = Field(default_factory=lambda: dt.datetime.now())


class BrowserWithContexts(BaseModel):
    model_config = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "arbitrary_types_allowed": True
    }

    browser_id: str
    browser: PlaywrightBrowser = Field(exclude=True)
    contexts: dict[str, TimeContext]
    resource_options: BrowserResourceOptions
    timestamp: dt.datetime = Field(default_factory=lambda: dt.datetime.now())
    cdp_url: str | None = None


class BaseBrowserPoolConfig(FrozenConfig):
    contexts_per_browser: int = 4
    viewport_width: int | None = None
    viewport_height: int | None = None
    verbose: bool = False


class BaseBrowserPool(PlaywrightResourceHandler, ABC):
    BROWSER_CREATION_TIMEOUT_SECONDS: ClassVar[int] = 30
    BROWSER_OPERATION_TIMEOUT_SECONDS: ClassVar[int] = 30

    config: BaseBrowserPoolConfig = BaseBrowserPoolConfig()
    browsers: dict[str, BrowserWithContexts] = Field(default_factory=dict)
    headless_browsers: dict[str, BrowserWithContexts] = Field(default_factory=dict)

    def available_browsers(self, headless: bool | None = None) -> dict[str, BrowserWithContexts]:
        if headless is None:
            return {**self.headless_browsers, **self.browsers}
        elif headless:
            return self.headless_browsers
        else:
            return self.browsers

    @override
    async def stop(self) -> None:
        """Stop the playwright instance"""
        await super().stop()
        self.browsers = {}
        self.headless_browsers = {}

    @abstractmethod
    async def create_playwright_browser(self, resource_options: BrowserResourceOptions) -> PlaywrightBrowser:
        pass

    @abstractmethod
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        pass

    async def create_browser(self, resource_options: BrowserResourceOptions) -> BrowserWithContexts:
        """Get an existing browser or create a new one if needed"""

        if resource_options.debug:
            port_manager = get_port_manager()

            # set port if nothing was set until now
            if resource_options.debug_port is None and port_manager is not None:
                debug_port = port_manager.acquire_port()
                if debug_port is None:
                    raise BrowserPoolNotStartedError()
                resource_options = resource_options.set_port(debug_port)

        browser = await self.create_playwright_browser(resource_options)
        browser_id = str(uuid.uuid4())
        _browser = BrowserWithContexts(
            browser_id=browser_id,
            browser=browser,
            contexts={},
            resource_options=resource_options,
        )
        # Store browser reference
        self.available_browsers(resource_options.headless)[browser_id] = _browser
        return _browser

    async def get_or_create_browser(self, resource_options: BrowserResourceOptions) -> BrowserWithContexts:
        """Find a browser with available space for a new context"""
        browsers = self.available_browsers(resource_options.headless)
        for browser in browsers.values():
            if len(browser.contexts) < self.config.contexts_per_browser:
                return browser
        # Create a new browser
        if self.config.verbose:
            logger.info(
                f"Maximum contexts per browser reached ({self.config.contexts_per_browser}). Creating new browser..."
            )
        browser = await self.create_browser(resource_options)
        return browser

    def create_context(self, browser: BrowserWithContexts, context: PlaywrightBrowserContext) -> str:
        context_id = str(uuid.uuid4())
        browser.contexts[context_id] = TimeContext(context_id=context_id, context=context)
        return context_id

    @override
    async def get_browser_resource(self, resource_options: BrowserResourceOptions) -> BrowserResource:
        browser = await self.get_or_create_browser(resource_options)

        try:
            async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                context = await browser.browser.new_context(
                    no_viewport=False,
                    viewport={
                        "width": self.config.viewport_width,
                        "height": self.config.viewport_height,
                    },  # pyright: ignore[reportArgumentType]
                    permissions=[
                        "clipboard-read",
                        "clipboard-write",
                    ],  # Needed for clipboard copy/paste to respect tabs / new lines
                    proxy=resource_options.proxy.to_playwright()
                    if resource_options.proxy is not None
                    else None,  # already specified at browser level, but might as well
                    user_agent=resource_options.user_agent,
                )
                if resource_options.cookies is not None:
                    if self.config.verbose:
                        logger.info(f"Adding cookies to browser {browser.browser_id}...")
                    for cookie in resource_options.cookies:
                        await context.add_cookies([cookie.model_dump()])  # type: ignore
                context_id = self.create_context(browser, context)
                if len(context.pages) == 0:
                    page = await context.new_page()
                else:
                    page = context.pages[-1]
                if browser.resource_options.debug_port is not None:
                    resource_options = resource_options.set_port(browser.resource_options.debug_port)
                return BrowserResource(
                    page=page,
                    context_id=context_id,
                    browser_id=browser.browser_id,
                    resource_options=resource_options,
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
        browsers = self.available_browsers(headless=browser.resource_options.headless)
        if browser.browser_id not in browsers:
            raise BrowserResourceNotFoundError(
                f"Browser '{browser.browser_id}' not found in available browsers (i.e {list(browsers.keys())})"
            )
        status = await self.close_playwright_browser(browser)
        if not status:
            logger.error(f"/!\\ VERY BAD THING HAPPENED: Failed to close browser {browser.browser_id}")
        port_manager = get_port_manager()
        if port_manager is not None and browser.resource_options.debug_port is not None:
            port_manager.release_port(browser.resource_options.debug_port)
        del browsers[browser.browser_id]

    @override
    async def release_browser_resource(self, resource: BrowserResource) -> None:
        browsers = self.available_browsers(resource.resource_options.headless)
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
            logger.error(f"Failed to close playright context: {e}")
            return
        del resource_browser.contexts[resource.context_id]
        if len(resource_browser.contexts) == 0:
            await self.release_browser(resource_browser)
