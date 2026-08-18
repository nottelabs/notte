from typing import TYPE_CHECKING, Any, cast

from notte_core.common.config import BrowserBackend, config

if TYPE_CHECKING:
    from patchright.async_api import Frame as PatchrightFrame
from notte_core.common.logging import logger

match config.browser_backend:
    case BrowserBackend.PLAYWRIGHT:
        from playwright.async_api import (
            Browser,
            BrowserContext,
            CDPSession,
            ConsoleMessage,
            Error,
            Frame,
            FrameLocator,
            Locator,
            Page,
            Playwright,
            Response,
            TimeoutError,
            async_playwright,
        )

        logger.info("⚙️ Browser backend set to 'playwright'. You can change it in the config.toml file.")
    case BrowserBackend.PATCHRIGHT:
        from patchright.async_api import (
            Browser,
            BrowserContext,
            CDPSession,
            ConsoleMessage,
            Error,
            Frame,
            FrameLocator,
            Locator,
            Page,
            Playwright,
            Response,
            TimeoutError,
            async_playwright,
        )
    case _:  # pyright: ignore[reportUnnecessaryComparison]
        raise ValueError(
            f"Invalid browser backend: {config.browser_backend}. Valid backends are {list(BrowserBackend)}."
        )  # pyright: ignore[reportUnreachable]


def getPlaywrightOrPatchrightTimeoutError() -> tuple[type[Exception], type[Exception]] | type[Exception]:
    errors: list[type[Exception]] = []
    try:
        from patchright.async_api import TimeoutError as _PatchrightTimeoutError

        errors.append(_PatchrightTimeoutError)
    except ImportError:
        pass
    try:
        from playwright.async_api import TimeoutError as _PlaywrightTimeoutError

        errors.append(_PlaywrightTimeoutError)
    except ImportError:
        pass
    if len(errors) == 1:
        return errors[0]
    elif len(errors) == 2:
        return errors[0], errors[1]
    else:
        raise RuntimeError("Unexpected number of errors")


def getPlaywrightOrPatchrightError() -> tuple[type[Exception], type[Exception]] | type[Exception]:
    errors: list[type[Exception]] = []
    try:
        from patchright.async_api import Error as _PatchrightError

        errors.append(_PatchrightError)
    except ImportError:
        pass
    try:
        from playwright.async_api import Error as _PlaywrightError

        errors.append(_PlaywrightError)
    except ImportError:
        pass
    if len(errors) == 1:
        return errors[0]
    elif len(errors) == 2:
        return errors[0], errors[1]
    else:
        raise RuntimeError("Unexpected number of errors")


async def evaluate_in_main_world(frame: Frame, expression: str) -> Any:
    """Evaluate JavaScript in a frame's page world for either browser backend."""
    if config.browser_backend == BrowserBackend.PATCHRIGHT:
        patchright_frame = cast("PatchrightFrame", frame)
        return await patchright_frame.evaluate(expression, isolated_context=False)
    return await frame.evaluate(expression)


__all__ = [
    "Browser",
    "BrowserContext",
    "Playwright",
    "async_playwright",
    "TimeoutError",
    "Error",
    "Frame",
    "Locator",
    "Response",
    "Page",
    "CDPSession",
    "FrameLocator",
    "ConsoleMessage",
    "evaluate_in_main_world",
]
