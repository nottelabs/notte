import os
import uuid
from dataclasses import dataclass
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
    browser_id: int
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
    browser: Browser
    contexts: dict[str, BrowserContext]
    headless: bool


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

        self._headless_browsers: list[BrowserWithContexts] = []
        self._browsers: list[BrowserWithContexts] = []
        self._playwright: Playwright | None = None

    def available_browsers(self, headless: bool | None = None) -> list[BrowserWithContexts]:
        if headless is None:
            return self._headless_browsers + self._browsers
        elif headless:
            return self._headless_browsers
        else:
            return self._browsers

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
            "open_contexts": sum(len(browser.contexts) for browser in self.available_browsers()),
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

    async def _create_browser(self, headless: bool = True) -> None:
        """Get an existing browser or create a new one if needed"""
        if self._playwright is None:
            await self.start()

        # Check if we can create more browsers
        if len(self.available_browsers()) >= self.max_browsers:
            # Could implement browser reuse strategy here
            raise RuntimeError(f"Maximum number of browsers ({self.max_browsers}) reached")

        # Calculate unique debug port for this browser
        current_debug_port = self.base_debug_port + len(self.available_browsers())
        if self._playwright is None:
            raise RuntimeError("Playwright not initialized. Call `start` first.")
        browser = await self._playwright.chromium.launch(
            headless=headless,
            args=(
                [
                    f"--remote-debugging-port={current_debug_port}",
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
        _browser = BrowserWithContexts(browser=browser, contexts={}, headless=headless)
        # Store browser reference
        self.available_browsers(headless).append(_browser)

    async def _create_context(self, headless: bool = True) -> tuple[str, BrowserContext]:
        """Create and track a new browser context"""
        browsers = self.available_browsers(headless)
        if len(browsers) == 0 or len(browsers[-1].contexts) >= self.max_total_contexts:
            if len(browsers) > 0:
                logger.info(f"Maximum number of contexts ({self.max_total_contexts}) reached. Creating new browser...")
            await self._create_browser(headless)

        context_id = str(uuid.uuid4())
        context = await browsers[-1].browser.new_context()
        browsers[-1].contexts[context_id] = context
        return context_id, context

    async def get_browser_resource(self, headless: bool = True) -> BrowserResource:
        context_id, context = await self._create_context(headless)
        page = await context.new_page()
        return BrowserResource(
            page=page, context_id=context_id, browser_id=len(self.available_browsers(headless)) - 1, headless=headless
        )

    async def release_browser_resource(self, resource: BrowserResource) -> None:
        await resource.page.close()
        browsers = self.available_browsers(resource.headless)
        resource_browser = browsers[resource.browser_id]
        await resource_browser.contexts[resource.context_id].close()
        del resource_browser.contexts[resource.context_id]
        if len(resource_browser.contexts) == 0:
            await resource_browser.browser.close()
            _ = browsers.pop(resource.browser_id)

    async def cleanup(self):
        """Cleanup all browser instances"""
        for browser in self.available_browsers():
            await browser.browser.close()
        self._headless_browsers = []
        self._browsers = []
        if self._playwright:
            await self._playwright.stop()
