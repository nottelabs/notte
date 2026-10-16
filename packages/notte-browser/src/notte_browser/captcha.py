from collections.abc import Awaitable, Callable

from notte_core.actions import CaptchaSolveAction

from notte_browser.errors import CaptchaSolverNotAvailableError
from notte_browser.window import BrowserWindow

CaptchaSolver = Callable[[BrowserWindow, CaptchaSolveAction], Awaitable[bool]]
_solver: CaptchaSolver | None = None


def set_captcha_solver(solver: CaptchaSolver | None) -> None:
    """Install a process-wide solver, or remove it with None."""
    global _solver
    _solver = solver


def captcha_solver_available() -> bool:
    return _solver is not None


async def solve_captcha(window: BrowserWindow, action: CaptchaSolveAction) -> bool:
    solver = _solver
    if solver is None:
        raise CaptchaSolverNotAvailableError()
    return await solver(window, action)
