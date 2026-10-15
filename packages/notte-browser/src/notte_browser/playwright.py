"""Launch owns a browser and driver; connect owns only its driver connection."""

import asyncio

from notte_core.config import config
from notte_core.logging import logger
from notte_core.profiling import profiler
from notte_core.types import LocalSessionStartRequest

from notte_browser.driver import Browser, BrowserContext, Page, Playwright, async_playwright
from notte_browser.errors import BrowserNotAvailableError, CdpConnectionError
from notte_browser.window import BrowserWindow, BrowserWindowOptions

BROWSER_CREATION_TIMEOUT_SECONDS = 30
BROWSER_OPERATION_TIMEOUT_SECONDS = 30


async def _connect_browser(driver: Playwright, options: BrowserWindowOptions) -> Browser:
    if options.cdp_url is None:
        raise ValueError("CDP URL is required to connect to a browser over CDP")
    try:
        match options.browser_type:
            case "chromium" | "chrome" | "chrome-nightly" | "chrome-turbo":
                return await driver.chromium.connect_over_cdp(options.cdp_url)
            case "firefox":
                return await driver.firefox.connect(options.cdp_url)
    except Exception as e:
        raise CdpConnectionError(options.cdp_url) from e


@profiler.profiled("PlaywrightManager.create_playwright_browser")
async def _launch_browser(driver: Playwright, options: BrowserWindowOptions) -> Browser:
    """Get an existing browser or create a new one if needed"""
    if options.cdp_url is not None:
        raise ValueError("CDP browser should not be created like other browsers")

    if config.verbose:
        if options.debug_port is not None:
            logger.info(f"🪟 [Browser Settings] Launching browser in debug mode on port {options.debug_port}")
        if options.cdp_url is not None:
            logger.info(f"🪟 [Browser Settings] Connecting to browser over CDP at {options.cdp_url}")
        if options.proxy is not None:
            logger.info(f"🪟 [Browser Settings] Using proxy {options.proxy.get('server', 'unknown')}")
        if options.browser_type == "firefox":
            logger.info(
                f"🪟 [Browser Settings] Using {options.browser_type} browser. Note that CDP may not be supported for this browser."
            )

    match options.browser_type:
        case "chromium" | "chrome":
            if options.headless and options.user_agent is None:
                logger.warning(
                    "🪟 [Browser Settings] Launching browser in headless without providing a user-agent"
                    + ", for better odds at evading bot detection, set a user-agent or run in headful mode"
                )
            browser = await driver.chromium.launch(
                channel="chrome"
                if options.browser_type == "chrome"
                else "chromium",  # opt in to new headless mode by setting chromium
                headless=options.headless,
                proxy=options.proxy,
                timeout=BROWSER_CREATION_TIMEOUT_SECONDS * 1000,
                args=options.get_chrome_args(),
            )
        case _:
            # TODO: add firefox support: this is not currently supported by patchright
            # browser = await driver.firefox.launch(
            #     headless=options.headless,
            #     proxy=options.proxy,
            #     timeout=BROWSER_CREATION_TIMEOUT_SECONDS * 1000,
            # )
            raise BrowserNotAvailableError(browser_type=options.browser_type)
    return browser


@profiler.profiled("PlaywrightManager.get_browser_resource")
async def _new_page(options: BrowserWindowOptions, browser: Browser) -> Page:
    async with asyncio.timeout(BROWSER_OPERATION_TIMEOUT_SECONDS):
        viewport = None
        if options.viewport_width is not None or options.viewport_height is not None:
            viewport = {
                "width": options.viewport_width,
                "height": options.viewport_height,
            }
        else:
            logger.warning(
                f"🪟 No viewport set in {'headless' if options.headless else 'headful'} mode, using default viewport in playwright"
            )

        context: BrowserContext = await browser.new_context(
            # no viewport should be False for headless browsers
            no_viewport=not options.headless,
            viewport=viewport,  # pyright: ignore[reportArgumentType]
            permissions=[
                # Needed for clipboard copy/paste to respect tabs / new lines for chromium browsers
                "clipboard-read",
                "clipboard-write",
            ]
            if options.browser_type in ["chromium", "chrome"]
            else [],
            proxy=options.proxy,
            user_agent=options.user_agent,
            extra_http_headers=options.extra_http_headers,
        )

        if len(context.pages) == 0:
            page = await context.new_page()
        else:
            page = context.pages[-1]
        return page


async def _start_driver() -> Playwright:
    async with profiler.profile("start_playwright"):
        return await async_playwright().start()


@profiler.profiled("PlaywrightManager.new_window")
async def launch(options: BrowserWindowOptions) -> BrowserWindow:
    """Launch a local browser; closing the window closes the browser and driver."""
    if options.cdp_url is not None:
        return await connect(options.cdp_url, options)
    driver = await _start_driver()
    browser: Browser | None = None
    try:
        browser = await _launch_browser(driver, options)
        page = await _new_page(options, browser)
        window = BrowserWindow(page, options)
    except BaseException:
        try:
            if browser is not None:
                await browser.close()
        finally:
            await driver.stop()
        raise
    window._owned_browser = browser  # pyright: ignore[reportPrivateUsage]
    window._owned_driver = driver  # pyright: ignore[reportPrivateUsage]
    window.on_close = window._close_owned  # pyright: ignore[reportPrivateUsage]
    return window


async def connect(cdp_url: str, options: BrowserWindowOptions | None = None) -> BrowserWindow:
    """Attach to an existing browser; closing the window only disconnects this driver."""
    options = (
        BrowserWindowOptions.from_request(LocalSessionStartRequest(cdp_url=cdp_url))
        if options is None
        else options.model_copy(update={"cdp_url": cdp_url})
    )
    driver = await _start_driver()
    try:
        browser = await _connect_browser(driver, options)
        if browser.contexts:
            context = browser.contexts[0]
            if options.extra_http_headers is not None:
                await context.set_extra_http_headers(options.extra_http_headers)
            page = context.pages[-1] if context.pages else await context.new_page()
        else:
            page = await _new_page(options, browser)
        window = BrowserWindow(page, options)
    except BaseException:
        await driver.stop()
        raise
    window._owned_driver = driver  # pyright: ignore[reportPrivateUsage]
    window.on_close = window._close_owned  # pyright: ignore[reportPrivateUsage]
    return window
