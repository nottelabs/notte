import datetime as dt
import os
import uuid
from dataclasses import dataclass, field
from typing import final

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
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
class BrowserWithContexts:
    browser_id: str
    browser: Browser
    contexts: dict[str, BrowserContext]
    headless: bool
    timestamp: dt.datetime = field(default_factory=lambda: dt.datetime.now())


@final
class BrowserPool:
    def __init__(self, base_debug_port: int = 9222, config: BrowserPoolConfig | None = None):
        self.base_debug_port = base_debug_port
        self.config = config if config is not None else BrowserPoolConfig()
        self.max_total_contexts = self.config.calculate_max_contexts()
        self.max_browsers = self.config.calculate_max_browsers()
        self.contexts_per_browser = int(self.max_total_contexts / self.max_browsers)

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
        self._last_browser_id: str = ""
        self._last_headless_browser_id: str = ""
        self._playwright: Playwright | None = None

    def available_browsers(self, headless: bool | None = None) -> dict[str, BrowserWithContexts]:
        if headless is None:
            return {**self._headless_browsers, **self._browsers}
        elif headless:
            return self._headless_browsers
        else:
            return self._browsers

    def get_last_browser_id(self, headless: bool) -> str:
        if headless:
            return self._last_headless_browser_id
        else:
            return self._last_browser_id

    def set_last_browser_id(self, browser_id: str, headless: bool) -> None:
        if headless:
            self._last_headless_browser_id = browser_id
        else:
            self._last_browser_id = browser_id

    async def start(self):
        """Initialize the playwright instance"""
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def check_sessions(self) -> dict[str, int]:
        """Check actual number of open browser instances and contexts."""
        if self._playwright is None:
            await self.start()

        # try:
        #     browsers = [
        #         await self._playwright.chromium.connect_over_cdp(f'http://localhost:{self.base_debug_port + i}')
        #         for i in range(len(self.available_browsers()))
        #     ]

        #     stats = {
        #         "browser_contexts": sum(len(browser.contexts) for browser in browsers),
        #         "pages": sum(len(context.pages) for browser in browsers for context in browser.contexts),
        #         "managed_browsers": len(self.available_browsers()),
        #         "managed_contexts": sum(len(browser.contexts) for browser in self.available_browsers()),
        #     }

        #     logger.debug(f"Browser pool stats: {stats}")
        #     return stats

        # except Exception as e:
        #     logger.error(f"Failed to check browser sessions: {e}")
        return {
            "open_browsers": len(self.available_browsers()),
            "open_contexts": sum(len(browser.contexts) for browser in self.available_browsers().values()),
        }

    async def check_memory_usage(self) -> dict[str, float]:
        """Monitor memory usage of browser contexts"""
        stats = await self.check_sessions()

        estimated_memory = (
            (stats["browser_contexts"] * self.config.CONTEXT_MEMORY)
            + (stats["pages"] * self.config.PAGE_MEMORY)
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
            "contexts_remaining": self.max_total_contexts - stats["browser_contexts"],
        }

    async def _create_browser(self, headless: bool) -> None:
        """Get an existing browser or create a new one if needed"""
        if self._playwright is None:
            await self.start()

        # Check if we can create more browsers
        if len(self.available_browsers()) >= self.max_browsers:
            # Could implement browser reuse strategy here
            raise RuntimeError(f"Maximum number of browsers ({self.max_browsers}) reached")

        # Calculate unique debug port for this browser
        # current_debug_port = self.base_debug_port + len(self.available_browsers())
        if self._playwright is None:
            raise RuntimeError("Playwright not initialized. Call `start` first.")
        browser = await self._playwright.chromium.launch(
            headless=headless,
            timeout=30000,
            args=(
                [
                    # f"--remote-debugging-port={current_debug_port}",
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
        self.set_last_browser_id(browser_id, headless)

    async def _create_context(self, headless: bool) -> tuple[str, BrowserContext]:
        """Create and track a new browser context"""
        browsers = self.available_browsers(headless)
        browser_id = self.get_last_browser_id(headless)
        if len(browsers) == 0 or len(browsers[browser_id].contexts) >= self.contexts_per_browser:
            if len(browsers) > 0:
                logger.info(
                    f"Maximum contexts per browser reached ({self.contexts_per_browser}). Creating new browser..."
                )
            await self._create_browser(headless)
            browser_id = self.get_last_browser_id(headless)

        context_id = str(uuid.uuid4())
        context = await browsers[browser_id].browser.new_context()
        browsers[browser_id].contexts[context_id] = context
        return context_id, context

    async def get_browser_resource(self, headless: bool) -> BrowserResource:
        context_id, context = await self._create_context(headless)
        page = await context.new_page()
        return BrowserResource(
            page=page, context_id=context_id, browser_id=self.get_last_browser_id(headless), headless=headless
        )

    async def release_browser_resource(self, resource: BrowserResource) -> None:
        browsers = self.available_browsers(resource.headless)
        if resource.browser_id not in browsers:
            raise RuntimeError(f"Browser {resource.browser_id} not found in available browsers.")
        resource_browser = browsers[resource.browser_id]
        if resource.context_id not in resource_browser.contexts:
            raise RuntimeError(f"Context {resource.context_id} not found in available contexts.")
        try:
            await resource_browser.contexts[resource.context_id].close()
        except Exception as e:
            logger.error(f"Failed to close context: {e}")
            return
        del resource_browser.contexts[resource.context_id]
        if len(resource_browser.contexts) == 0:
            logger.info(f"Closing browser {resource.browser_id}")
            try:
                await resource_browser.browser.close()
            except Exception as e:
                logger.error(f"Failed to close browser: {e}")
            del browsers[resource.browser_id]
            if len(browsers) == 0:
                self.set_last_browser_id("", resource.headless)
            else:
                # set browser id with the latest timestamp
                latest_browser = max(browsers.values(), key=lambda x: x.timestamp)
                self.set_last_browser_id(latest_browser.browser_id, resource.headless)

    async def cleanup(self):
        """Cleanup all browser instances"""
        for browser in self.available_browsers().values():
            await browser.browser.close()
        self._headless_browsers = {}
        self._browsers = {}
        self._last_browser_id = ""
        self._last_headless_browser_id = ""
        if self._playwright:
            await self._playwright.stop()
