from notte_core.actions import (
    CaptchaSolveAction,
)

from notte_browser.window import BrowserWindow


class CaptchaHandler:
    @staticmethod
    async def handle_captchas(window: BrowserWindow, action: CaptchaSolveAction) -> bool:  # pyright: ignore [reportUnusedParameter]
        return True
