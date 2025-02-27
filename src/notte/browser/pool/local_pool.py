import asyncio
import datetime as dt
import os
from typing import final

from loguru import logger
from patchright.async_api import Browser
from typing_extensions import override

from notte.browser.pool.base import BaseBrowserPool, BrowserResource, BrowserWithContexts
from notte.errors.browser import (
    BrowserResourceLimitError,
)


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

    @classmethod
    def calculate_contexts_per_browser(cls) -> int:
        return int(cls.calculate_max_contexts() / cls.calculate_max_browsers())

    @classmethod
    def create_browser_args(cls, disable_web_security: bool) -> list[str]:
        browser_args = [
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--no-zygote",
            "--mute-audio",
            f'--js-flags="--max-old-space-size={int(cls.CONTEXT_MEMORY)}"',
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
        ]

        if disable_web_security:
            browser_args.extend(
                [
                    "--disable-web-security",
                    "--disable-site-isolation-trials",
                    "--disable-features=IsolateOrigins,site-per-process",
                ]
            )
        return browser_args


@final
class LocalBrowserPool(BaseBrowserPool):
    def __init__(
        self,
        base_debug_port: int = 9222,
        config: BrowserPoolConfig | None = None,
        disable_web_security: bool = False,
        verbose: bool = False,
    ):
        self.base_debug_port = base_debug_port
        self.config = config if config is not None else BrowserPoolConfig()
        self.max_total_contexts = self.config.calculate_max_contexts()
        self.max_browsers = self.config.calculate_max_browsers()
        super().__init__(self.config.calculate_contexts_per_browser(), verbose)
        if self.verbose:
            logger.info(
                (
                    "Initializing BrowserPool with:"
                    f"\n - Container Memory: {self.config.CONTAINER_MEMORY}MB"
                    f"\n - Available Memory: {self.config.get_available_memory()}MB"
                    f"\n - Max Contexts: {self.max_total_contexts}"
                    f"\n - Max Browsers: {self.max_browsers}"
                    f"\n - Contexts per Browser: {self.config.calculate_contexts_per_browser()}"
                )
            )
        self._browser_args = self.config.create_browser_args(disable_web_security)

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

    @override
    async def create_playwright_browser(self, headless: bool) -> Browser:
        """Get an existing browser or create a new one if needed"""
        # Check if we can create more browsers
        if len(self.available_browsers()) >= self.max_browsers:
            # Could implement browser reuse strategy here
            raise BrowserResourceLimitError(f"Maximum number of browsers ({self.max_browsers}) reached")

        # Calculate unique debug port for this browser
        current_debug_port = self.base_debug_port + len(self.available_browsers())
        browser_args = self._browser_args + [f"--remote-debugging-port={current_debug_port}"]

        browser = await self.playwright.chromium.launch(
            headless=headless,
            timeout=self.BROWSER_CREATION_TIMEOUT_SECONDS * 1000,
            args=browser_args,
        )
        return browser

    @override
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        if not force and (dt.datetime.now() - browser.timestamp) < dt.timedelta(
            seconds=self.BROWSER_CREATION_TIMEOUT_SECONDS
        ):
            if self.verbose:
                logger.info(
                    (
                        f"Browser {browser.browser_id} has been open for less than "
                        f"{self.BROWSER_CREATION_TIMEOUT_SECONDS} seconds. Skipping..."
                    )
                )
            return True
        try:
            async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                await browser.browser.close()
        except Exception as e:
            logger.error(f"Failed to close browser: {e}")
        return False

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
                _ = await self.close_playwright_browser(browser, force=force)
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
                    _ = await self.close_playwright_browser(browser, force=force)
        self._headless_browsers = {}
        self._browsers = {}
