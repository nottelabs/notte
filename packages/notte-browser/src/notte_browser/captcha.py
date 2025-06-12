from notte_core.actions import (
    CaptchaSolveAction,
)

from notte_browser.window import BrowserWindow


class CaptchaHandler:
    @staticmethod
    async def handle_captchas(window: BrowserWindow, action: CaptchaSolveAction) -> bool:  # pyright: ignore [reportUnusedParameter]
        _ = await window.page.wait_for_function(
            """
    () => {
        const element = document.querySelector('.antigate_solver');
        console.log(element.textContent.trim())
        return element && element.textContent.trim() === 'Solved by notte';
    }
""",
            timeout=0,
        )
        return True
