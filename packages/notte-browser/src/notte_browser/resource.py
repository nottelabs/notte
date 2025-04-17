import asyncio
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import ClassVar, Self

from loguru import logger
from notte_core.common.config import FrozenConfig
from notte_sdk.types import BrowserType, Cookie, ProxySettings
from openai import BaseModel
from patchright.async_api import (
    Browser as PlaywrightBrowser,
)
from patchright.async_api import (
    BrowserContext,
    Playwright,
    async_playwright,
)
from patchright.async_api import (
    Page as PlaywrightPage,
)
from pydantic import Field, PrivateAttr
from typing_extensions import override

from notte_browser.errors import (
    BrowserNotStartedError,
    BrowserPoolNotStartedError,
)


@dataclass(frozen=True)
class BrowserResourceOptions:
    headless: bool
    user_agent: str | None = None
    proxy: ProxySettings | None = None
    debug: bool = False
    debug_port: int | None = None
    cookies: list[Cookie] | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    cdp_url: str | None = None
    browser_type: BrowserType = BrowserType.CHROMIUM
    chrome_args: list[str] | None = None

    def set_port(self, port: int) -> "BrowserResourceOptions":
        options = dict(asdict(self), debug_port=port, debug=True)
        return BrowserResourceOptions(**options)


class BrowserResource(BaseModel):
    model_config = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "arbitrary_types_allowed": True
    }

    page: PlaywrightPage = Field(exclude=True)
    resource_options: BrowserResourceOptions
    # TODO:check if this is needed
    cdp_url: str | None = None
    browser_id: str | None = None
    context_id: str | None = None


class BrowserResourceHandlerConfig(FrozenConfig):
    base_debug_port: int = 9222
    web_security: bool = False
    max_browsers: int | None = None
    max_total_contexts: int | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    custom_devtools_frontend: str | None = None
    default_chromium_args: list[str] = [
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--no-zygote",
        "--mute-audio",
        '--js-flags="--max-old-space-size=100"',
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
    ]
    security_chromium_args: list[str] = [
        "--disable-web-security",
        "--disable-site-isolation-trials",
        "--disable-features=IsolateOrigins,site-per-process",
        "--remote-allow-origins=*",
    ]

    def set_web_security(self: Self, value: bool = True) -> Self:
        return self._copy_and_validate(web_security=value)

    def disable_web_security(self: Self) -> Self:
        return self.set_web_security(False)

    def enable_web_security(self: Self) -> Self:
        return self.set_web_security(True)

    def set_base_debug_port(self: Self, value: int) -> Self:
        return self._copy_and_validate(base_debug_port=value)

    def set_chromium_args(self: Self, value: list[str] | None) -> Self:
        return self._copy_and_validate(default_chromium_args=value)

    def set_viewport_width(self: Self, value: int) -> Self:
        return self._copy_and_validate(viewport_width=value)

    def set_viewport_height(self: Self, value: int) -> Self:
        return self._copy_and_validate(viewport_height=value)

    def get_chromium_args(self, chrome_args: list[str] | None = None, cdp_port: int | None = None) -> list[str]:
        # chrome args override default + security
        if chrome_args is not None:
            chromium_args = chrome_args.copy()
        else:
            chromium_args = self.default_chromium_args.copy()
            if not self.web_security:
                chromium_args.extend(self.security_chromium_args)

        if self.custom_devtools_frontend is not None:
            chromium_args.extend(
                [
                    f"--custom-devtools-frontend={self.custom_devtools_frontend}",
                ]
            )

        if cdp_port is not None:
            chromium_args.append(f"--remote-debugging-port={cdp_port}")

        return chromium_args


class PlaywrightResourceHandler(BaseModel, ABC):
    model_config = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "arbitrary_types_allowed": True
    }
    BROWSER_CREATION_TIMEOUT_SECONDS: ClassVar[int] = 30
    BROWSER_OPERATION_TIMEOUT_SECONDS: ClassVar[int] = 30

    _playwright: Playwright | None = PrivateAttr(default=None)

    async def start(self) -> None:
        """Initialize the playwright instance"""
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def stop(self) -> None:
        """Stop the playwright instance"""
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def is_started(self) -> bool:
        return self._playwright is not None

    @property
    def playwright(self) -> Playwright:
        if self._playwright is None:
            raise BrowserPoolNotStartedError()
        return self._playwright

    def set_playwright(self, playwright: Playwright) -> None:
        self._playwright = playwright

    async def connect_cdp_browser(self, resource_options: BrowserResourceOptions) -> PlaywrightBrowser:
        if resource_options.cdp_url is None:
            raise ValueError("CDP URL is required to connect to a browser over CDP")
        match resource_options.browser_type:
            case BrowserType.CHROMIUM:
                return await self.playwright.chromium.connect_over_cdp(resource_options.cdp_url)
            case BrowserType.FIREFOX:
                return await self.playwright.firefox.connect(resource_options.cdp_url)

    @abstractmethod
    async def get_browser_resource(self, resource_options: BrowserResourceOptions) -> BrowserResource:
        pass

    @abstractmethod
    async def release_browser_resource(self, resource: BrowserResource) -> None:
        pass


class BrowserResourceHandler(PlaywrightResourceHandler):
    config: BrowserResourceHandlerConfig = Field(default_factory=BrowserResourceHandlerConfig)
    browser: PlaywrightBrowser | None = None

    async def create_playwright_browser(self, resource_options: BrowserResourceOptions) -> PlaywrightBrowser:
        """Get an existing browser or create a new one if needed"""
        if resource_options.cdp_url is not None:
            return await self.connect_cdp_browser(resource_options)

        if self.config.verbose:
            if resource_options.debug:
                logger.info(f"[Browser Settings] Launching browser in debug mode on port {resource_options.debug_port}")
            if resource_options.cdp_url is not None:
                logger.info(f"[Browser Settings] Connecting to browser over CDP at {resource_options.cdp_url}")
            if resource_options.proxy is not None:
                logger.info(f"[Browser Settings] Using proxy {resource_options.proxy.server}")
            if resource_options.browser_type != BrowserType.CHROMIUM:
                logger.info(
                    f"[Browser Settings] Using {resource_options.browser_type} browser. Note that CDP may not be supported for this browser."
                )

        match resource_options.browser_type:
            case BrowserType.CHROMIUM:
                browser_args = self.config.get_chromium_args(
                    chrome_args=resource_options.chrome_args, cdp_port=resource_options.debug_port
                )

                if resource_options.headless and resource_options.user_agent is None:
                    logger.warning(
                        "Launching browser in headless without providing a user-agent"
                        + ", for better odds at evading bot detection, set a user-agent or run in headful mode"
                    )

                browser = await self.playwright.chromium.launch(
                    headless=resource_options.headless,
                    proxy=resource_options.proxy.to_playwright() if resource_options.proxy is not None else None,
                    timeout=self.BROWSER_CREATION_TIMEOUT_SECONDS * 1000,
                    args=browser_args,
                )
            case BrowserType.FIREFOX:
                browser = await self.playwright.firefox.launch(
                    headless=resource_options.headless,
                    proxy=resource_options.proxy.to_playwright() if resource_options.proxy is not None else None,
                    timeout=self.BROWSER_CREATION_TIMEOUT_SECONDS * 1000,
                )
        self.browser = browser
        return browser

    async def close_playwright_browser(self, browser: PlaywrightBrowser | None = None) -> bool:
        _browser = browser or self.browser
        if _browser is None:
            raise BrowserNotStartedError()
        try:
            async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
                await _browser.close()
                return True
        except Exception as e:
            logger.error(f"Failed to close window: {e}")
        self.browser = None
        return False

    @override
    async def get_browser_resource(self, resource_options: BrowserResourceOptions) -> BrowserResource:
        if self.browser is None:
            self.browser = await self.create_playwright_browser(resource_options)
        async with asyncio.timeout(self.BROWSER_OPERATION_TIMEOUT_SECONDS):
            viewport = None
            if self.config.viewport_width is not None or self.config.viewport_height is not None:
                viewport = {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                }

            context: BrowserContext = await self.browser.new_context(
                # no viewport should be False for headless browsers
                no_viewport=not resource_options.headless,
                viewport=viewport,  # pyright: ignore[reportArgumentType]
                permissions=[
                    "clipboard-read",
                    "clipboard-write",
                ],  # Needed for clipboard copy/paste to respect tabs / new lines
                proxy=resource_options.proxy.to_playwright() if resource_options.proxy is not None else None,
                user_agent=resource_options.user_agent,
            )
            if resource_options.cookies is not None:
                if self.config.verbose:
                    logger.info("Adding cookies to browser...")
                for cookie in resource_options.cookies:
                    await context.add_cookies([cookie.model_dump()])  # type: ignore

            if len(context.pages) == 0:
                page = await context.new_page()
            else:
                page = context.pages[-1]
            return BrowserResource(
                page=page,
                resource_options=resource_options,
            )

    @override
    async def release_browser_resource(self, resource: BrowserResource) -> None:
        context: BrowserContext = resource.page.context
        await context.close()
