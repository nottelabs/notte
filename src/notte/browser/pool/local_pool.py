import asyncio
import datetime as dt
import os
from typing import Self, final

from loguru import logger
from patchright.async_api import Browser as PatchrightBrowser
from pydantic import Field
from typing_extensions import override

from notte.browser.pool.base import (
    BaseBrowserPool,
    BrowserResource,
    BrowserWithContexts,
)
from notte.common.config import FrozenConfig
from notte.errors.browser import (
    BrowserResourceLimitError,
)


class MemoryBrowserPoolConfig(FrozenConfig):
    # Memory allocations in MB
    container_memory: int = Field(default_factory=lambda: int(os.getenv("CONTAINER_MEMORY_MB", "4096")))  # Default 4GB
    system_reserved: int = Field(
        default_factory=lambda: int(os.getenv("SYSTEM_RESERVED_MB", "1024"))
    )  # Default 1GB reserved

    # Base memory requirements (headless mode)
    base_browser_memory: int = Field(default_factory=lambda: int(os.getenv("BASE_BROWSER_MEMORY_MB", "150")))
    context_memory: int = Field(default_factory=lambda: int(os.getenv("CONTEXT_MEMORY_MB", "35")))
    page_memory: int = Field(default_factory=lambda: int(os.getenv("PAGE_MEMORY_MB", "40")))

    # Safety margin (percentage of total memory to keep free)
    safety_margin: float = Field(
        default_factory=lambda: float(os.getenv("MEMORY_SAFETY_MARGIN", "0.2"))
    )  # Default 20% safety margin

    def set_container_memory(self: Self, value: int) -> Self:
        return self._copy_and_validate(container_memory=value)

    def set_system_reserved(self: Self, value: int) -> Self:
        return self._copy_and_validate(system_reserved=value)

    def set_base_browser_memory(self: Self, value: int) -> Self:
        return self._copy_and_validate(base_browser_memory=value)

    def set_context_memory(self: Self, value: int) -> Self:
        return self._copy_and_validate(context_memory=value)

    def set_page_memory(self: Self, value: int) -> Self:
        return self._copy_and_validate(page_memory=value)

    def set_safety_margin(self: Self, value: float) -> Self:
        return self._copy_and_validate(safety_margin=value)

    def get_available_memory(self) -> int:
        """Calculate total available memory for Playwright"""
        return self.container_memory - self.system_reserved

    def calculate_max_contexts(self) -> int:
        """Calculate maximum number of contexts based on available memory"""
        available_memory = self.get_available_memory() * (1 - self.safety_margin)
        memory_per_context = self.context_memory + self.page_memory
        return int(available_memory / memory_per_context)

    def calculate_max_browsers(self) -> int:
        """Calculate optimal number of browser instances"""
        max_contexts = self.calculate_max_contexts()
        contexts_per_browser = int(os.getenv("CONTEXTS_PER_BROWSER", "4"))
        return max(1, max_contexts // contexts_per_browser)

    def calculate_contexts_per_browser(self) -> int:
        return int(self.calculate_max_contexts() / self.calculate_max_browsers())


class BrowserPoolConfig(FrozenConfig):
    memory: MemoryBrowserPoolConfig = MemoryBrowserPoolConfig()
    base_debug_port: int = 9222
    web_security: bool = False
    max_browsers: int | None = None
    max_total_contexts: int | None = None
    chromium_args: list[str] | None = None
    viewport_width: int = 1280
    viewport_height: int = 1020  # Default in playright is 720

    def set_web_security(self: Self, value: bool = True) -> Self:
        return self._copy_and_validate(web_security=value)

    def disable_web_security(self: Self) -> Self:
        return self.set_web_security(False)

    def enable_web_security(self: Self) -> Self:
        return self.set_web_security(True)

    def set_memory(self: Self, value: MemoryBrowserPoolConfig) -> Self:
        return self._copy_and_validate(memory=value)

    def set_base_debug_port(self: Self, value: int) -> Self:
        return self._copy_and_validate(base_debug_port=value)

    def set_max_browsers(self: Self, value: int | None) -> Self:
        return self._copy_and_validate(max_browsers=value)

    def set_max_total_contexts(self: Self, value: int | None) -> Self:
        return self._copy_and_validate(max_total_contexts=value)

    def set_chromium_args(self: Self, value: list[str] | None) -> Self:
        return self._copy_and_validate(chromium_args=value)

    def set_viewport_width(self: Self, value: int) -> Self:
        return self._copy_and_validate(viewport_width=value)

    def set_viewport_height(self: Self, value: int) -> Self:
        return self._copy_and_validate(viewport_height=value)

    def get_max_contexts(self) -> int:
        if self.max_total_contexts is not None:
            return self.max_total_contexts
        return self.memory.calculate_max_contexts()

    def get_max_browsers(self) -> int:
        if self.max_browsers is not None:
            return self.max_browsers
        return self.memory.calculate_max_browsers()

    def get_contexts_per_browser(self) -> int:
        if self.max_total_contexts is not None:
            return self.max_total_contexts // self.get_max_browsers()
        return self.memory.calculate_contexts_per_browser()

    def get_chromium_args(self, offset_base_debug_port: int = 0) -> list[str]:
        port = f"--remote-debugging-port={self.base_debug_port + offset_base_debug_port}"
        if self.chromium_args is not None:
            return self.chromium_args + [port]
        # create chromium args
        chromium_args = [
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--no-zygote",
            "--mute-audio",
            f'--js-flags="--max-old-space-size={int(self.memory.context_memory)}"',
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
        ]

        if not self.web_security:
            chromium_args.extend(
                [
                    "--disable-web-security",
                    "--disable-site-isolation-trials",
                    "--disable-features=IsolateOrigins,site-per-process",
                ]
            )
        return chromium_args + [port]

    def estimate_memory_usage(self, n_contexts: int, n_browsers: int) -> int:
        return (
            (n_contexts * self.memory.context_memory)
            + (n_contexts * self.memory.page_memory)
            + (n_browsers * self.memory.base_browser_memory)
        )


class LocalBrowserPool(BaseBrowserPool):
    def __init__(self, config: BrowserPoolConfig | None = None):
        self.config: BrowserPoolConfig = config if config is not None else BrowserPoolConfig()
        super().__init__(
            contexts_per_browser=self.config.get_contexts_per_browser(),
            viewport_width=self.config.viewport_width,
            viewport_height=self.config.viewport_height,
            verbose=self.config.verbose,
        )
        if self.config.verbose:
            logger.info(
                (
                    "Initializing BrowserPool with:"
                    f"\n - Container Memory: {self.config.memory.container_memory}MB"
                    f"\n - Available Memory: {self.config.memory.get_available_memory()}MB"
                    f"\n - Max Contexts: {self.config.get_max_contexts}"
                    f"\n - Max Browsers: {self.config.get_max_browsers}"
                    f"\n - Contexts per Browser: {self.config.get_contexts_per_browser}"
                )
            )

    def check_sessions(self) -> dict[str, int]:
        """Check actual number of open browser instances and contexts."""

        return {
            "open_browsers": len(self.available_browsers()),
            "open_contexts": sum(len(browser.contexts) for browser in self.available_browsers().values()),
        }

    def check_memory_usage(self) -> dict[str, float]:
        """Monitor memory usage of browser contexts"""
        stats = self.check_sessions()

        estimated_memory = self.config.estimate_memory_usage(
            stats["open_contexts"],
            len(self.available_browsers()),
        )

        available_memory = self.config.memory.get_available_memory()

        return {
            **stats,
            "container_memory_mb": self.config.memory.container_memory,
            "available_memory_mb": available_memory,
            "estimated_memory_mb": estimated_memory,
            "memory_usage_percentage": (estimated_memory / available_memory) * 100,
            "contexts_remaining": self.config.get_max_contexts() - stats["open_contexts"],
        }

    @override
    async def create_playwright_browser(self, headless: bool) -> PatchrightBrowser:
        """Get an existing browser or create a new one if needed"""
        # Check if we can create more browsers
        if len(self.available_browsers()) >= self.config.get_max_browsers():
            # Could implement browser reuse strategy here
            raise BrowserResourceLimitError(f"Maximum number of browsers ({self.config.get_max_browsers}) reached")

        browser_args = self.config.get_chromium_args(offset_base_debug_port=len(self.available_browsers()))

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
            logger.error(f"Failed to close window: {e}")
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
        if len(self.available_browsers()) == 0:
            # manually resart the pool to kill any dangling processes
            # we can do that because we know that the pool is empty
            await self.stop()
            await self.start()


@final
class SingleLocalBrowserPool(LocalBrowserPool):
    @override
    async def get_browser_resource(self, headless: bool) -> BrowserResource:
        # start the pool automatically for single browser pool
        await self.start()
        return await super().get_browser_resource(headless)

    @override
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        _ = await super().close_playwright_browser(browser, force)
        # for local pool, closing one browser will stop the whole pool
        await self.stop()
        return True
