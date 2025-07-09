from typing import ClassVar

from notte_core.actions import (
    CaptchaSolveAction,
)

from notte_browser.errors import CaptchaSolverNotAvailableError
from notte_browser.window import BrowserWindow


class CaptchaHandler:
    is_available: ClassVar[bool] = False

    @staticmethod
    async def handle_captchas(window: BrowserWindow, action: CaptchaSolveAction) -> bool:  # pyright: ignore [reportUnusedParameter]
        """Meant to be reimplemented if used"""
        raise CaptchaSolverNotAvailableError()
