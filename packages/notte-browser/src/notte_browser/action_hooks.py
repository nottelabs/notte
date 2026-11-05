"""Caller code that runs around the input of `notte_browser.execution`.

Subclass `ActionHooks`, override the methods you need, and install it for the process (`install_action_hooks`)
or for the code that runs inside a block (`use_action_hooks`, which takes precedence over the process hooks).
With no hooks installed, execution calls nothing.

Each hook call is bounded by the time it is given. A hook that raises, or that is still running when its time
is up, is stopped and logged at debug level, and the action goes on as it would have without it. A hook stops on
`asyncio` cancellation: one that swallows `CancelledError` can delay the action past its bound.
"""

import asyncio
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar

from notte_core.logging import logger

from notte_browser.driver import Locator, Page

Point = tuple[float, float]

# Time an `after_navigation` call is given (s)
AFTER_NAVIGATION_TIMEOUT_S = 1.0


class ActionHooks:
    """Hooks called by `notte_browser.execution`. Every method does nothing by default."""

    async def before_click(self, page: Page, locator: Locator, time_left_s: float) -> None:
        """Called before the pointer click of a click action is dispatched, once its element was located and
        found enabled. The click then moves the pointer to the element and presses it, as it would have without
        the hook: the driver does not report this move through `pointer_moved`. `time_left_s` is what the click
        can spare of its timeout, and bounds this call."""
        del page, locator, time_left_s

    async def after_navigation(self, page: Page, time_left_s: float) -> None:
        """Called once an action that navigated has settled, with the page now acted on: after a goto (in the
        current or a new tab), back, forward or reload, after any action during which the page's main frame
        navigated (a new document, one restored from the back-forward cache, or a URL change within it), and after an action that switched to another page (a tab it opened or switched to). Several
        calls can concern the same document. `time_left_s` bounds this call."""
        del page, time_left_s

    def pointer_moved(self, page: Page, point: Point | None) -> None:
        """Called when an action moved the pointer of `page` itself, outside of `before_click`: `point` is where
        it went in viewport coordinates, None when that is not known (the driver moved it onto an element to
        click, check or hover it). Called synchronously, right after the move."""
        del page, point


_process_hooks: ActionHooks | None = None
_SCOPED_HOOKS: ContextVar[ActionHooks | None] = ContextVar("notte_action_hooks", default=None)


def install_action_hooks(hooks: ActionHooks | None) -> ActionHooks | None:
    """Installs `hooks` for the whole process (None removes them). Returns the hooks installed before."""
    global _process_hooks
    previous, _process_hooks = _process_hooks, hooks
    return previous


@contextmanager
def use_action_hooks(hooks: ActionHooks) -> Generator[None]:
    """Uses `hooks` for the actions executed inside the block (in the current task and the tasks it creates),
    in place of the process hooks."""
    token = _SCOPED_HOOKS.set(hooks)
    try:
        yield
    finally:
        _SCOPED_HOOKS.reset(token)


def active_action_hooks() -> ActionHooks | None:
    """The hooks the actions executed here use, None when there are none."""
    scoped = _SCOPED_HOOKS.get()
    return scoped if scoped is not None else _process_hooks


async def _bounded(name: str, call: Callable[[], Awaitable[None]], time_left_s: float) -> None:
    if time_left_s <= 0:
        return
    try:
        async with asyncio.timeout(time_left_s):
            await call()
    except Exception as error:
        # a hook never fails its action, its own timeout included
        logger.debug(f"Action hook {name} skipped: {type(error).__name__}")


async def run_before_click(hooks: ActionHooks, page: Page, locator: Locator, time_left_s: float) -> None:
    await _bounded("before_click", lambda: hooks.before_click(page, locator, time_left_s), time_left_s)


async def run_after_navigation(hooks: ActionHooks, page: Page) -> None:
    time_left_s = AFTER_NAVIGATION_TIMEOUT_S
    await _bounded("after_navigation", lambda: hooks.after_navigation(page, time_left_s), time_left_s)


def notify_pointer_moved(page: Page, point: Point | None) -> None:
    """Tells the active hooks, if any, that the pointer of `page` moved to `point`."""
    hooks = active_action_hooks()
    if hooks is None:
        return
    try:
        hooks.pointer_moved(page, point)
    except Exception as error:
        logger.debug(f"Action hook pointer_moved skipped: {type(error).__name__}")
