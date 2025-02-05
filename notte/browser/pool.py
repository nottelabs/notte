import asyncio
import datetime as dt
import os
import uuid
from dataclasses import dataclass, field
from typing import final

from loguru import logger
from patchright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from notte.errors.browser import (
    BrowserNotStartedError,
    BrowserResourceLimitError,
    BrowserResourceNotFoundError,
)


@dataclass
class BrowserResource:
    page: Page
    browser_id: str
    context_id: str
    headless: bool


@final
class BrowserPoolConfig:
    # Memory allocations in MB
    CONTAINER_MEMORY = int(os.getenv("CONTAINER_MEMORY_MB", "4096"))  # Default 4GB
    SYSTEM_RESERVED = int(os.getenv("SYSTEM_RESERVED_MB", "1024"))  # Default 1GB reserved

    # Base memory requirements (headless mode)
    BASE_BROWSER_MEMORY = int(os.getenv("BASE_BROWSER_MEMORY_MB", "150"))
    CONTEXT_MEMORY = int(os.getenv("CONTEXT_MEMORY_MB", "35"))
    PAGE_MEMORY = int(os.getenv("PAGE_MEMORY_MB", "40"))

    # Safety margin (percentage of total memory to keep free)
    SAFETY_MARGIN = float(os.getenv("MEMORY_SAFETY_MARGIN", "0.2"))  # 20% by default

    @classmethod
    def get_available_memory(cls) -> int:
        """Calculate total available memory for Playwright"""
        return cls.CONTAINER_MEMORY - cls.SYSTEM_RESERVED

    @classmethod
    def calculate_max_contexts(cls) -> int:
        """Calculate maximum number of contexts based on available memory"""
        available_memory = cls.get_available_memory() * (1 - cls.SAFETY_MARGIN)
        memory_per_context = cls.CONTEXT_MEMORY + cls.PAGE_MEMORY
        return int(available_memory / memory_per_context)

    @classmethod
    def calculate_max_browsers(cls) -> int:
        """Calculate optimal number of browser instances"""
        max_contexts = cls.calculate_max_contexts()
        contexts_per_browser = int(os.getenv("CONTEXTS_PER_BROWSER", "4"))
        return max(1, max_contexts // contexts_per_browser)


@dataclass
class TimeContext:
    context_id: str
    context: BrowserContext
    timestamp: dt.datetime = field(default_factory=lambda: dt.datetime.now())


@dataclass
class BrowserWithContexts:
    browser_id: str
    browser: Browser
    contexts: dict[str, TimeContext]
    headless: bool
    timestamp: dt.datetime = field(default_factory=lambda: dt.datetime.now())


@final
class BrowserPool:
    BROWSER_CREATION_TIMEOUT_SECONDS = 30
    BROWSER_OPERATION_TIMEOUT_SECONDS = 30

    def __init__(
        self,
        base_debug_port: int = 9222,
        config: BrowserPoolConfig | None = None,
        verbose: bool = False,
    ):
        self.base_debug_port = base_debug_port
        self.config = config if config is not None else BrowserPoolConfig()
        self.max_total_contexts = self.config.calculate_max_contexts()
        self.max_browsers = self.config.calculate_max_browsers()
        self.contexts_per_browser = int(self.max_total_contexts / self.max_browsers)
        self.verbose = verbose
        if self.verbose:
            logger.info(
                (
                    f"Initializing BrowserPool with:"
                    f"\n - Container Memory: {self.config.CONTAINER_MEMORY}MB"
                    f"\n - Available Memory: {self.config.get_available_memory()}MB"
                    f"\n - Max Contexts: {self.max_total_contexts}"
                    f"\n - Max Browsers: {self.max_browsers}"
                    f"\n - Contexts per Browser: {self.contexts_per_browser}"
                )
            )

        self._headless_browsers: dict[str, BrowserWithContexts] = {}
        self._browsers: dict[str, BrowserWithContexts] = {}
        self._playwright: Playwright | None = None

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

    def check_sessions(self) -> dict[str, int]:
        """Check actual number of open browser instances and contexts."""

        return {
            "open_browsers": len(self.available_browsers()),
            "open_contexts": sum(len(browser.contexts) for browser in self.available_browsers().values()),
        }

    def check_memory_usage(self) -> dict[str, float]:
        """Monitor memory usage of browser contexts"""
        stats = self.check_sessions()

        estimated_memory = (
            (stats["open_contexts"] * self.config.CONTEXT_MEMORY)
            + (stats["open_contexts"] * self.config.PAGE_MEMORY)
            + (len(self._headless_browsers) * self.config.BASE_BROWSER_MEMORY)
            + (len(self._browsers) * self.config.BASE_BROWSER_MEMORY)
        )

        available_memory = self.config.get_available_memory()

        return {
            **stats,
            "container_memory_mb": self.config.CONTAINER_MEMORY,
            "available_memory_mb": available_memory,
            "estimated_memory_mb": estimated_memory,
            "memory_usage_percentage": (estimated_memory / available_memory) * 100,
            "contexts_remaining": self.max_total_contexts - stats["open_contexts"],
        }

    async def _create_browser(self, headless: bool) -> BrowserWithContexts:
        """Get an existing browser or create a new one if needed"""
        if self._playwright is None:
            await self.start()

        # Check if we can create more browsers
        if len(self.available_browsers()) >= self.max_browsers:
            # Could implement browser reuse strategy here
            raise BrowserResourceLimitError(f"Maximum number of browsers ({self.max_browsers}) reached")

        # Calculate unique debug port for this browser
        # current_debug_port = self.base_debug_port + len(self.available_browsers())
        if self._playwright is None:
            raise BrowserNotStartedError()
        browser = await self._playwright.chromium.launch(
            headless=headless,
            timeout=self.BROWSER_CREATION_TIMEOUT_SECONDS * 1000,
            args=(
                [
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--no-zygote",
                    "--mute-audio",
                    f'--js-flags="--max-old-space-size={int(self.config.CONTEXT_MEMORY)}"',
                ]
                if headless
                else []
            ),
        )
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

    async def _find_browser_with_space(self, headless: bool) -> BrowserWithContexts | None:
        """Find a browser with available space for a new context"""
        browsers = self.available_browsers(headless)
        for browser in browsers.values():
            if len(browser.contexts) < self.contexts_per_browser:
                return browser
        return None

    async def get_browser_resource(self, headless: bool) -> BrowserResource:
        """Create and track a new browser context"""
        browser = await self._find_browser_with_space(headless)
        if browser is None:
            if self.verbose:
                logger.info(
                    f"Maximum contexts per browser reached ({self.contexts_per_browser}). Creating new browser..."
                )
            browser = await self._create_browser(headless)

        context_id = str(uuid.uuid4())
        try:
            async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                context = await browser.browser.new_context()
                browser.contexts[context_id] = TimeContext(context_id=context_id, context=context)
                page = await context.new_page()
                return BrowserResource(
                    page=page, context_id=context_id, browser_id=browser.browser_id, headless=headless
                )
        except Exception as e:
            logger.error(f"Failed to create browser resource: {e}")
            # Cleanup on failure
            if context_id in browser.contexts:
                try:
                    await browser.contexts[context_id].context.close()
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
            logger.error(f"Failed to close context: {e}")
            return
        del resource_browser.contexts[resource.context_id]
        if len(resource_browser.contexts) == 0:
            await self._close_browser(resource.browser_id, resource.headless)

    async def _close_browser(self, browser_id: str, headless: bool, force: bool = True) -> None:
        logger.info(f"Closing browser {browser_id}")
        browsers = self.available_browsers(headless)
        if not force and (dt.datetime.now() - browsers[browser_id].timestamp) < dt.timedelta(
            seconds=self.BROWSER_CREATION_TIMEOUT_SECONDS
        ):
            if self.verbose:
                logger.info(
                    (
                        f"Browser {browser_id} has been open for less than "
                        f"{self.BROWSER_CREATION_TIMEOUT_SECONDS} seconds. Skipping..."
                    )
                )
            return
        try:
            async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                await browsers[browser_id].browser.close()
        except Exception as e:
            logger.error(f"Failed to close browser: {e}")
        del browsers[browser_id]

    async def cleanup(self, except_resources: list[BrowserResource] | None = None, force: bool = True) -> None:
        """Cleanup all browser instances"""

        except_resources_ids: dict[str, set[str]] = {
            resource.browser_id: set() for resource in (except_resources or [])
        }
        for resource in except_resources or []:
            except_resources_ids[resource.browser_id].add(resource.context_id)

        for browser in self.available_browsers().values():
            if browser.browser_id not in except_resources_ids:
                if except_resources is not None:
                    logger.info(f"Closing browser {browser.browser_id} because it is not in except_resources")
                await self._close_browser(browser.browser_id, browser.headless, force=force)
            else:
                # close all contexts except the ones in except_resources_ids[browser.browser_id]
                context_ids = list(browser.contexts.keys())
                for context_id in context_ids:
                    if context_id not in except_resources_ids[browser.browser_id]:
                        context = browser.contexts[context_id]
                        should_skip = not force and (dt.datetime.now() - context.timestamp) < dt.timedelta(
                            seconds=self.BROWSER_CREATION_TIMEOUT_SECONDS
                        )
                        if should_skip:
                            if self.verbose:
                                logger.info(
                                    (
                                        f"Skipping context {context_id} of browser {browser.browser_id} "
                                        "because it has been open for "
                                        f"less than {self.BROWSER_CREATION_TIMEOUT_SECONDS} s"
                                    )
                                )
                            continue
                        if except_resources is not None:
                            if self.verbose:
                                logger.info(
                                    (
                                        f"Closing context {context_id} of browser {browser.browser_id} "
                                        "because it is not in except_resources"
                                    )
                                )
                        await context.context.close()
                        del browser.contexts[context_id]
                if len(browser.contexts) == 0:
                    await self._close_browser(browser.browser_id, browser.headless)
