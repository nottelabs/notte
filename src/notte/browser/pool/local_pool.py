import asyncio
import datetime as dt
import os
from typing import Any, Self

from loguru import logger
from patchright.async_api import Browser as PatchrightBrowser
from pydantic import Field
from typing_extensions import override

from notte.browser.pool.base import (
    BaseBrowserPool,
    BaseBrowserPoolConfig,
    BrowserResource,
    BrowserWithContexts,
)
from notte.browser.pool.ports import PortManager
from notte.common.config import FrozenConfig
from notte.errors.browser import (
    BrowserResourceLimitError,
)


class MemoryBrowserPoolConfig(FrozenConfig):
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


class BrowserPoolConfig(FrozenConfig):
    memory: MemoryBrowserPoolConfig = MemoryBrowserPoolConfig()
    base_debug_port: int = 9222
    web_security: bool = False
    max_browsers: int | None = None
    max_total_contexts: int | None = None
    chromium_args: list[str] | None = None
    viewport_width: int = 1280
    viewport_height: int = 1020  # Default in playright is 720
    custom_devtools_frontend: str | None = None

    def disable_web_security(self: Self) -> Self:
        return self._copy_and_validate(web_security=False)

    def enable_web_security(self: Self) -> Self:
        return self._copy_and_validate(web_security=True)

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

    def get_chromium_args(self, cdp_port: int) -> list[str]:
        port = f"--remote-debugging-port={cdp_port}"
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
            f'--js-flags="--max-old-space-size={int(cls.CONTEXT_MEMORY)}"',
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
                    "--remote-allow-origins=*",
                ]
            )
        if self.custom_devtools_frontend is not None:
            chromium_args.extend(
                [
                    f"--custom-devtools-frontend={self.custom_devtools_frontend}",
                ]
            )
        return chromium_args + [port]

    def estimate_memory_usage(self, n_contexts: int, n_browsers: int) -> int:
        return (
            (n_contexts * self.memory.context_memory)
            + (n_contexts * self.memory.page_memory)
            + (n_browsers * self.memory.base_browser_memory)
        )


@final
class LocalBrowserPool(BaseBrowserPool):
    local_config: BrowserPoolConfig = Field(default_factory=BrowserPoolConfig)

    @override
    def model_post_init(self, __context: Any):
        PortManager().reset(start=self.local_config.base_debug_port, nb=self.local_config.get_max_browsers())
        self.config: BaseBrowserPoolConfig = BaseBrowserPoolConfig(
            contexts_per_browser=self.local_config.get_contexts_per_browser(),
            viewport_width=self.local_config.viewport_width,
            viewport_height=self.local_config.viewport_height,
            verbose=self.local_config.verbose,
        )
        if self.local_config.verbose:
            logger.info(
                (
                    "Initializing BrowserPool with:"
                    f"\n - Container Memory: {self.local_config.memory.container_memory}MB"
                    f"\n - Available Memory: {self.local_config.memory.get_available_memory()}MB"
                    f"\n - Max Contexts: {self.local_config.get_max_contexts()}"
                    f"\n - Max Browsers: {self.local_config.get_max_browsers()}"
                    f"\n - Contexts per Browser: {self.local_config.get_contexts_per_browser()}"
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

        estimated_memory = self.local_config.estimate_memory_usage(
            n_contexts=stats["open_contexts"],
            n_browsers=len(self.available_browsers()),
        )

        available_memory = self.local_config.memory.get_available_memory()

        return {
            **stats,
            "container_memory_mb": self.local_config.memory.container_memory,
            "available_memory_mb": available_memory,
            "estimated_memory_mb": estimated_memory,
            "memory_usage_percentage": (estimated_memory / available_memory) * 100,
            "contexts_remaining": self.local_config.get_max_contexts() - stats["open_contexts"],
        }

    @override
    async def create_playwright_browser(self, headless: bool, port: int | None) -> PatchrightBrowser:
        """Get an existing browser or create a new one if needed"""
        # Check if we can create more browsers
        if len(self.available_browsers()) >= self.local_config.get_max_browsers():
            # Could implement browser reuse strategy here
            raise BrowserResourceLimitError(
                f"Maximum number of browsers ({self.local_config.get_max_browsers()}) reached"
            )
        if port is None:
            raise ValueError("Port is required in LocalBrowserPool")
        browser_args = self.local_config.get_chromium_args(cdp_port=port)

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
            if self.config.verbose:
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
                return True
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
        nb_browsers = len(self.available_browsers())
        for browser in self.available_browsers().values():
            if browser.browser_id not in except_resources_ids or len(except_resources_ids[browser.browser_id]) == 0:
                if except_resources is not None:
                    logger.info(f"Closing browser {browser.browser_id} because it is not in except_resources")
                await self.release_browser(browser)
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
                            if self.config.verbose:
                                logger.info(
                                    (
                                        f"Skipping context {context_id} of browser {browser.browser_id} "
                                        "because it has been open for "
                                        f"less than {self.BROWSER_CREATION_TIMEOUT_SECONDS} s"
                                    )
                                )
                            continue
                        if self.config.verbose:
                            logger.info(
                                (
                                    f"Closing context {context_id} of browser {browser.browser_id} "
                                    "because it is not in except_resources"
                                )
                            )

                        await self.release_browser_resource(
                            BrowserResource(
                                page=context.context.pages[0],
                                browser_id=browser.browser_id,
                                context_id=context_id,
                                headless=browser.headless,
                            )
                        )
                if len(browser.contexts) == 0:
                    await self.release_browser(browser)
        if len(self.available_browsers()) == 0 and nb_browsers > 0:
            # manually resart the pool to kill any dangling processes
            # we can do that because we know that the pool is empty
            await self.stop()
            await self.start()


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
