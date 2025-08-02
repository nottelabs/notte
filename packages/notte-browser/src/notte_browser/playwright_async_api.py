from loguru import logger

try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        CDPSession,
        Error,
        FrameLocator,
        Locator,
        Page,
        Playwright,
        TimeoutError,
        async_playwright,
    )

    logger.info("⚙️ Prioritized 'playwright' over 'patchright'. Uninstall 'playwright' to default to 'patchright'.")
except ImportError:
    from patchright.async_api import (
        Browser,
        BrowserContext,
        CDPSession,
        Error,
        FrameLocator,
        Locator,
        Page,
        Playwright,
        TimeoutError,
        async_playwright,
    )


def getPlaywrightOrPatchrightTimeoutError() -> tuple[type[Exception], type[Exception]] | type[Exception]:
    from patchright.async_api import TimeoutError as _PatchrightTimeoutError

    try:
        from playwright.async_api import TimeoutError as _PlaywrightTimeoutError

        return _PatchrightTimeoutError, _PlaywrightTimeoutError
    except ImportError:
        return _PatchrightTimeoutError


def getPlaywrightOrPatchrightError() -> tuple[type[Exception], type[Exception]] | type[Exception]:
    from patchright.async_api import Error as _PatchrightError

    try:
        from playwright.async_api import Error as _PlaywrightError

        return _PatchrightError, _PlaywrightError
    except ImportError:
        return _PatchrightError


__all__ = [
    "Browser",
    "BrowserContext",
    "Playwright",
    "async_playwright",
    "TimeoutError",
    "Error",
    "Locator",
    "Page",
    "CDPSession",
    "FrameLocator",
]
