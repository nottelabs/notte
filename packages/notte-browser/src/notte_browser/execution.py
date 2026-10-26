import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Literal

from notte_core.actions import (
    BaseAction,
    BrowserAction,
    CaptchaSolveAction,
    CheckAction,
    ClickAction,
    CloseTabAction,
    CompletionAction,
    DownloadFileAction,
    EvaluateJsAction,
    FallbackFillAction,
    FillAction,
    FormFillAction,
    GoBackAction,
    GoForwardAction,
    GotoAction,
    GotoNewTabAction,
    HelpAction,
    InteractionAction,
    MultiFactorFillAction,
    PressKeyAction,
    # ReadFileAction,
    ReloadAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    SwitchTabAction,
    UploadFileAction,
    WaitAction,
    # WriteFileAction,
)
from notte_core.config import config
from notte_core.credentials.types import get_str_value
from notte_core.dom_tree import DomNode, NodeSelectors
from notte_core.errors import (
    ActionExecutionError,
    FileChooserOpenedError,
    NotteTimeoutError,
    SnapshotProcessingError,
)
from notte_core.logging import logger
from notte_core.profiling import profiler
from notte_core.snapshot import BrowserSnapshot
from notte_core.storage import BaseStorage

from notte_browser.captcha import solve_captcha
from notte_browser.dom.locate import locate_element, selectors_through_shadow_dom
from notte_browser.dom.parsing import parse_dom
from notte_browser.driver import ElementHandle, Error, FileChooser, Frame, JSHandle, Locator
from notte_browser.errors import (
    InvalidLocatorRuntimeError,
    NoHistoryEntryError,
    PlaywrightTimeoutError,
    ScrollActionFailedError,
    capture_playwright_errors,
)
from notte_browser.files import download_file, upload_file
from notte_browser.form_filling import FormFiller
from notte_browser.js import script
from notte_browser.resolution import resolve_selectors
from notte_browser.settle import LONG_GRACE_MS, PageSettle
from notte_browser.window import BrowserWindow

_BLUR_ACTIVE_ELEMENT = script("blur_active_element.js")
_IS_DISABLED = script("is_disabled.js")
_PASTE_TEXT = script("paste_text.js")
# Page-side implementation: js/file_input_clicks.js
_FILE_INPUT_CLICKS = script("file_input_clicks.js")


def text_contains_tabs(text: str) -> bool:
    """
    Determine if a given text has significant indentation patterns.

    Args:
        text (str): The text to analyze

    Returns:
        bool: True if the text has significant indentation patterns, False otherwise
    """
    if not text or text.isspace():
        return False

    # Split into lines and remove empty lines
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return False

    # Count lines with leading whitespace or tabs
    indented_lines: int = sum(1 for line in lines if line.startswith((" ", "\t")))

    return indented_lines >= 1


def platform_control_key() -> Literal["Meta", "Control"]:
    """
    Returns the platform-specific control key modifier.

    Returns:
        Literal["Meta", "Control"]: "Meta" for macOS (Darwin), "Control" for other platforms
    """
    import platform

    return "Meta" if platform.system() == "Darwin" else "Control"


# Page-side implementation: js/scroll_tracker.js
_SCROLL_TRACKER = script("scroll_tracker.js")

# Page-side implementation: js/scroll_boundary.js
_SCROLL_BOUNDARY = script("scroll_boundary.js")

# Page-side implementation: js/largest_scroller.js
_LARGEST_SCROLLER = script("largest_scroller.js")
_FRAME_SCROLL_CLIP = script("frame_scroll_clip.js")
_FRAME_SCROLL_HIT = script("frame_scroll_hit.js")

# A scroll that has not started `SCROLL_START_MS` after the wheel failed; one that started has ended once its
# position is the same `SCROLL_STABLE_MS` apart (a smooth scroll, a scroll-snap), at most `SCROLL_CAP_MS` after it.
SCROLL_START_MS = 200
SCROLL_STABLE_MS = 50
SCROLL_POLL_MS = 25
SCROLL_CAP_MS = 1_000


async def _scroll_ended(
    read: Callable[[], Awaitable[tuple[bool, list[list[float | None]]]]], *, deadline: float | None = None
) -> bool:
    """Whether a scroll happened, once it has ended or failed to start. `read` returns whether the scroll started,
    and the positions it moves."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    last: list[list[float | None]] | None = None
    stable_since = start
    scrolled = False
    scope = asyncio.timeout_at(deadline if deadline is not None else start + SCROLL_CAP_MS / 1000)
    try:
        async with scope:
            while True:
                scrolled, positions = await read()
                now = loop.time()
                if positions != last:
                    last, stable_since = positions, now
                elapsed_ms = (now - start) * 1000
                if scrolled and (now - stable_since) * 1000 >= SCROLL_STABLE_MS:
                    return True
                if (not scrolled and elapsed_ms >= SCROLL_START_MS) or elapsed_ms >= SCROLL_CAP_MS:
                    return scrolled
                await asyncio.sleep(SCROLL_POLL_MS / 1000)
    except TimeoutError:
        if not scope.expired():
            raise
        return scrolled


def _scroll_context_disappeared(frame: Frame, error: Error) -> bool:
    return frame.is_detached() or any(
        message in str(error).lower()
        for message in (
            "execution context was destroyed",
            "cannot find context with specified id",
            "frame was detached",
        )
    )


# Page-side implementation: js/move_caret_to_end.js
_MOVE_CARET_TO_END = script("move_caret_to_end.js")

_IS_TEXT_FORM_CONTROL = "(el) => el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement"

# Page-side implementation: js/find_dropdown_option.js
_FIND_DROPDOWN_OPTION = script("find_dropdown_option.js")


async def _scroll_container_point(window: BrowserWindow, delta: int) -> tuple[float, float] | None:
    """Where to send a wheel that should scroll by `delta`: the center of the visible part of the scroll container with
    the largest visible area that can still move that way (`js/largest_scroller.js`), in the page or one of its frames,
    in page coordinates. None when there is none. Frames are clipped by each parent document's viewport and ancestors."""
    page = window.page
    best: tuple[float, float, float] | None = None
    for frame in page.frames:
        parents: list[tuple[ElementHandle, tuple[float, float], tuple[float, float]]] = []
        try:
            origin, scale = (0.0, 0.0), (1.0, 1.0)
            if frame is page.main_frame:
                clip = None
            else:
                width, height = await page.evaluate("() => [window.innerWidth, window.innerHeight]")
                clip = {"left": 0.0, "top": 0.0, "right": float(width), "bottom": float(height)}
                ancestors: list[Frame] = []
                ancestor = frame
                while ancestor.parent_frame is not None:
                    ancestors.append(ancestor)
                    ancestor = ancestor.parent_frame
                for ancestor in reversed(ancestors):
                    element = await ancestor.frame_element()
                    parents.append((element, origin, scale))
                    visible = await element.evaluate(_FRAME_SCROLL_CLIP)
                    if visible is None:
                        clip["right"] = clip["left"]
                        break
                    for edge in ("left", "top", "right", "bottom"):
                        axis = 0 if edge in ("left", "right") else 1
                        intersect = max if edge in ("left", "top") else min
                        clip[edge] = intersect(clip[edge], origin[axis] + visible[edge] * scale[axis])
                    origin = (origin[0] + visible["originX"] * scale[0], origin[1] + visible["originY"] * scale[1])
                    scale = (scale[0] * visible["scaleX"], scale[1] * visible["scaleY"])
                if clip["right"] <= clip["left"] or clip["bottom"] <= clip["top"]:
                    continue
                # Convert the visible intersection in page coordinates into this frame's coordinates.
                clip = {
                    "left": (clip["left"] - origin[0]) / scale[0],
                    "top": (clip["top"] - origin[1]) / scale[1],
                    "right": (clip["right"] - origin[0]) / scale[0],
                    "bottom": (clip["bottom"] - origin[1]) / scale[1],
                }
            found = await frame.evaluate(_LARGEST_SCROLLER, {"delta": delta, "clip": clip})
            if found is None:
                continue
            candidate = (
                origin[0] + found["x"] * scale[0],
                origin[1] + found["y"] * scale[1],
                found["area"] * scale[0] * scale[1],
            )
            if best is not None and candidate[2] <= best[2]:
                continue
            for element, parent_origin, parent_scale in parents:
                point = {
                    "x": (candidate[0] - parent_origin[0]) / parent_scale[0],
                    "y": (candidate[1] - parent_origin[1]) / parent_scale[1],
                }
                if not await element.evaluate(_FRAME_SCROLL_HIT, point):
                    break
            else:
                best = candidate
        except Error as error:
            if not _scroll_context_disappeared(frame, error):
                raise
            continue
        finally:
            for element, _, _ in parents:
                with suppress(Error):
                    await element.dispose()
    return None if best is None else (best[0], best[1])


class _ActionBudget:
    """What is left of an action's timeout, as a Playwright `timeout=` (milliseconds, never 0 = infinite)."""

    def __init__(self, deadline: float) -> None:
        self._deadline: float = deadline  # event loop time, in seconds

    def remaining_ms(self, keep_ms: float = 0) -> float:
        """Remaining budget, minus `keep_ms` held back for a later step (e.g. a fallback)."""
        remaining = (self._deadline - asyncio.get_running_loop().time()) * 1000
        return max(1.0, remaining - keep_ms)


async def _clear_focused_field(window: BrowserWindow) -> None:
    await window.page.keyboard.press(key=f"{platform_control_key()}+A")
    await window.short_wait()
    await window.page.keyboard.press(key="Backspace")
    await window.short_wait()


async def _select_custom_dropdown_option(
    window: BrowserWindow, locator: Locator, value: str, budget: _ActionBudget
) -> None:
    """Open a non-`<select>` dropdown and click the option matching `value`."""
    try:
        _ = await locator.click(timeout=budget.remaining_ms())
    except Exception as e:
        raise ActionExecutionError("select_dropdown", window.page.url, reason="Invalid selector") from e
    # The options may render a little after the click (animation, lazy list).
    deadline = asyncio.get_running_loop().time() + min(budget.remaining_ms(), 2000) / 1000
    while True:
        handle = await locator.evaluate_handle(_FIND_DROPDOWN_OPTION, value, timeout=budget.remaining_ms())
        try:
            option = handle.as_element()
            if option is not None:
                await option.click(timeout=budget.remaining_ms())
                return
        finally:
            with suppress(Error):  # the click may have navigated away
                await handle.dispose()
        if asyncio.get_running_loop().time() >= deadline:
            raise ActionExecutionError(
                "select_dropdown", window.page.url, reason=f"No dropdown option matches {value!r}"
            )
        await window.page.wait_for_timeout(100)


async def _append_text(window: BrowserWindow, locator: Locator, text: str, timeout: float) -> None:
    """Type `text` after the element's current content instead of replacing it."""
    if await locator.evaluate(_IS_TEXT_FORM_CONTROL, timeout=timeout):
        existing = await locator.input_value(timeout=timeout)
        await locator.fill(existing + text, timeout=timeout, force=True)
        return
    # contenteditable and other editable elements
    await locator.focus(timeout=timeout)
    await locator.evaluate(_MOVE_CARET_TO_END, timeout=timeout)
    await window.page.keyboard.insert_text(text)


_SLIDER_VALUE = script("slider_value.js")
# the most keys pressed to move a slider to a value
MAX_SLIDER_KEYS = 200
# how long the update of a key is waited for (a slider that re-renders) before the key is taken as doing nothing
SLIDER_KEY_WAIT_MS = 500
# the keys that move a slider up and down, tried in this order. A pair that moves the other way is swapped (a
# reversed or right-to-left slider)
_SLIDER_KEYS = (("PageUp", "PageDown"), ("ArrowUp", "ArrowDown"), ("ArrowRight", "ArrowLeft"))
_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


async def _move_slider(
    window: BrowserWindow, locator: Locator, value: str, slider: dict[str, float | None], budget: _ActionBudget
) -> None:
    """Move an ARIA slider or spinbutton (`role="slider"` / `role="spinbutton"`, which `fill` cannot set) to the number
    in `value` with its keyboard, as https://www.w3.org/WAI/ARIA/apg/patterns/slider/ and
    https://www.w3.org/WAI/ARIA/apg/patterns/spinbutton/ define it: Home / End for its ends, Page Up / Down while they
    do not go past the value, then the arrows, reading `aria-valuenow` after each key. A value between two steps
    ends on the closest step. `slider` is what `slider_value.js` read."""
    match = _NUMBER.search(value.replace(",", ""))
    if match is None:
        raise ActionExecutionError("fill", window.page.url, reason=f"A slider takes a number, not {value!r}")
    now, low, high = slider["now"], slider["min"], slider["max"]
    if now is None:
        raise ActionExecutionError("fill", window.page.url, reason="The slider has no aria-valuenow")
    target = float(match.group())
    if low is not None:
        target = max(target, low)
    if high is not None:
        target = min(target, high)

    def reached(current: float) -> bool:
        return abs(current - target) <= 1e-9 * max(1.0, abs(target))

    async def press(key: str, before: float) -> float:
        # the locator focuses the slider it finds now: one that re-renders can replace its element
        await locator.press(key, timeout=budget.remaining_ms())
        deadline = time.monotonic() + min(SLIDER_KEY_WAIT_MS, budget.remaining_ms()) / 1000
        while True:
            state = await locator.evaluate(_SLIDER_VALUE, timeout=budget.remaining_ms())
            after = None if state is None else state["now"]
            if after is None:
                raise ActionExecutionError("fill", window.page.url, reason="The slider lost its aria-valuenow")
            if after != before or time.monotonic() >= deadline:
                return after
            await asyncio.sleep(0.05)

    if not reached(now) and target in (low, high):
        now = await press("Home" if target == low else "End", now)
    moved = False
    for page_keys, (increase, decrease) in zip((True, False, False), _SLIDER_KEYS):
        swapped = False
        for _ in range(MAX_SLIDER_KEYS):
            if reached(now):
                return
            up = target > now
            after = await press(increase if up else decrease, now)
            if after == now:
                # this pair does nothing (or no more): try the next one
                break
            moved = True
            if (after > now) != up:
                if swapped:
                    break
                # this pair moves the other way
                increase, decrease, swapped = decrease, increase, True
                now = after
                continue
            if (after > target) == up and not reached(after):
                if page_keys:
                    # Page Up / Down went past the value: the arrows come back from there
                    now = after
                    break
                # between two steps: the closer one
                if abs(after - target) > abs(now - target):
                    _ = await press(decrease if up else increase, after)
                return
            now = after
        else:
            if reached(now):
                return
            raise ActionExecutionError(
                "fill", window.page.url, reason=f"The slider did not reach {value!r} in {MAX_SLIDER_KEYS} keys"
            )
    if not reached(now):
        reason = "The slider does not move with its keyboard" if not moved else f"The slider did not reach {value!r}"
        raise ActionExecutionError("fill", window.page.url, reason=reason)


async def _scroll_target(window: BrowserWindow, action: ScrollUpAction | ScrollDownAction) -> None:
    assert action.selector is not None
    locator = window.page.locator(action.selector)
    target = await locator.evaluate_handle(
        "element => element === document.documentElement ? document.scrollingElement : element",
        timeout=config.timeout_action_ms,
    )
    try:
        amount = action.amount
        if amount is None:
            amount = int(await target.evaluate("element => element.clientHeight") * 0.7)
        delta = -amount if isinstance(action, ScrollUpAction) else amount
        if delta == 0 or await target.evaluate(_SCROLL_BOUNDARY, delta):
            logger.info("Scroll target is already at its boundary; no movement needed.")
            return
        before = await target.evaluate("element => element.scrollTop")
        # Address the container directly: a wheel at its center can hit a nested
        # scroller, and hovering an offscreen target can move its parents.
        await target.evaluate("(element, delta) => element.scrollBy({top: delta, behavior: 'instant'})", delta)

        async def read() -> tuple[bool, list[list[float | None]]]:
            position: float = await target.evaluate("element => element.scrollTop")
            return position != before, [[position]]

        deadline = asyncio.get_running_loop().time() + SCROLL_CAP_MS / 1000
        if not await _scroll_ended(read, deadline=deadline):
            scope = asyncio.timeout_at(deadline)
            try:
                async with scope:
                    boundary = await target.evaluate(_SCROLL_BOUNDARY, delta)
            except TimeoutError as error:
                if not scope.expired():
                    raise
                raise ScrollActionFailedError() from error
            if not boundary:
                raise ScrollActionFailedError()
    finally:
        with suppress(Error):
            await target.dispose()


# Records whether the document goes through its own history (a `pushState` or hash entry) until disposed
_WATCH_POPSTATE = """() => {
    const watch = {moved: false};
    const onPopstate = () => { watch.moved = true };
    addEventListener('popstate', onPopstate, {once: true});
    watch.dispose = () => removeEventListener('popstate', onPopstate);
    return watch;
}"""


async def _traverse_history(window: BrowserWindow, operation: Literal["back", "forward"]) -> None:
    """Go back or forward in the tab's history. Fails when the tab has no page there (a tab opened by a link has no
    previous page): the browser then loads nothing, and the URL and the document stay the same."""
    url = window.page.url
    try:
        watch = await window.page.evaluate_handle(_WATCH_POPSTATE)
    except Error:
        # navigating already: the traversal is not checked
        watch = None
    try:
        await window.goto_and_wait(operation=operation, wait_until="commit")
        if watch is None or window.goto_response is not None or window.page.url != url:
            return
        try:
            moved = await watch.evaluate("watch => watch.moved")
        except Error:
            # another document replaced the watched one
            return
        if not moved:
            raise NoHistoryEntryError(operation)
    finally:
        if watch is not None:
            with suppress(Error):
                await watch.evaluate("watch => watch.dispose()")
            with suppress(Error):
                await watch.dispose()


def _can_create_tab(action: BaseAction) -> bool:
    """
    Check if an action can potentially create a new browser tab.
    Only actions that can open links or navigate can create tabs.
    """
    match action:
        case ClickAction() | GotoAction() | GotoNewTabAction() | PressKeyAction():
            # these actions can potentially create a new tab
            # click -> button can open in new tab (target="_blank")
            # goto -> navigation can potentially open in new tab
            # goto_new_tab -> explicitly creates a new tab
            # press_key -> pressing a key can potentially open a new tab (i.e press enter to submit a form)
            return True
        case _:
            return False


def _settles(action: BaseAction) -> bool:
    """Whether the page's reaction to an action is waited for (`notte_browser.settle`): the actions that can start
    a navigation, a goto that waits for the page's load (the default), and a scroll (what it loads)."""
    if isinstance(action, GotoAction):
        return _settled_goto(action)
    return isinstance(
        action,
        (
            InteractionAction,
            PressKeyAction,
            GoBackAction,
            GoForwardAction,
            ReloadAction,
            ScrollUpAction,
            ScrollDownAction,
        ),
    )


def _settled_goto(action: GotoAction) -> bool:
    """A goto that waits for the load (the default): its page is waited for like a click's new page. With another
    `wait_until`, it waits for that event, then sleeps as before."""
    return action.wait_until in (None, "load")


async def _settle(
    settle: PageSettle, action: BaseAction, url: str, *, verbose: bool, new_document: bool = False
) -> None:
    """Until the page has reacted to `action`, which ran on `url`."""
    match action:
        # a new page is waited for until its requests are done (the network going idle), whatever submitted it
        case ClickAction() | PressKeyAction() | InteractionAction(press_enter=True):
            await settle.wait(grace_ms=LONG_GRACE_MS, document="requests")
        case GotoAction():
            # what the page fetches after its load is waited for, instead of a fixed sleep
            await settle.wait(
                grace_ms=LONG_GRACE_MS,
                document="requests",
                new_document=new_document,
                url_changed=not new_document and settle.page.url != url,
            )
        case ScrollUpAction() | ScrollDownAction():
            # the scroll has ended: what it starts loading right away (more items, lazy content) is waited for
            await settle.wait()
        case GoBackAction() | GoForwardAction():
            await settle.wait(document="loaded")
        case ReloadAction():
            await settle.wait(document="requests")
        case InteractionAction() if settle.page.url != url:
            if verbose:
                logger.info(f"🪦 Page navigation detected for action {action.id}, waiting for the page to settle")
            await settle.wait(grace_ms=0, document="requests")
        case _:
            pass


@profiler.profiled("BrowserController.execute_browser_action", service_name="execution")
async def execute_browser_action(window: BrowserWindow, action: BaseAction, *, verbose: bool = False) -> bool:
    match action:
        case FormFillAction(value=value):
            form_filler = FormFiller(window.page)
            unpacked_values = {k: get_str_value(v) for k, v in value.items()}
            fill_results = await form_filler.fill_form(unpacked_values)
            if not any(isinstance(field, Locator) for field in fill_results.values()):
                statuses = ", ".join(f"{key}: {status}" for key, status in fill_results.items())
                raise ActionExecutionError(
                    action.type, window.page.url, reason=f"no form field could be filled ({statuses})"
                )

        case CaptchaSolveAction(captcha_type=_):
            _ = await solve_captcha(window, action)
        case GotoAction(url=url, wait_until=wait_until):
            # the load is waited for by `execute`, which settles the page
            await window.goto(url, wait_until="commit" if _settled_goto(action) else wait_until)
        case GotoNewTabAction(url=url):
            new_page = await window.page.context.new_page()
            window.page = new_page
            await window.goto(url=url)
        case SwitchTabAction(tab_index=tab_index):
            await window.switch_tab(tab_index, verbose=verbose)
        case CloseTabAction():
            await window.page.close()
        case WaitAction(time_ms=time_ms):
            await window.page.wait_for_timeout(time_ms)
        # the load is waited for by `execute`, which settles the page
        case GoBackAction():
            await _traverse_history(window, "back")
        case GoForwardAction():
            await _traverse_history(window, "forward")
        case ReloadAction():
            _ = await window.page.reload()
        case PressKeyAction(key=key):
            await window.page.keyboard.press(key)
        case ScrollUpAction(amount=amount) | ScrollDownAction(amount=amount):
            # blur the active element to prevent scroll from being blocked by the element
            await window.page.evaluate(_BLUR_ACTIVE_ELEMENT)
            if action.selector is not None:
                await _scroll_target(window, action)
                return True
            trackers: list[tuple[Frame, JSHandle]] = []
            try:
                # Wheel events stay in their frame, so observe each document.
                for frame in window.page.frames:
                    try:
                        trackers.append((frame, await frame.evaluate_handle(_SCROLL_TRACKER)))
                    except Error as error:
                        if not _scroll_context_disappeared(frame, error):
                            raise
                if amount is None:
                    viewport_height = await window.page.evaluate("window.innerHeight")
                    amount = int(viewport_height * 0.7)
                delta = -amount if isinstance(action, ScrollUpAction) else amount
                await window.page.mouse.wheel(delta_x=0, delta_y=delta)

                async def read() -> tuple[bool, list[list[float | None]]]:
                    scrolled = False
                    positions: list[list[float | None]] = []
                    for frame, tracker in trackers:
                        try:
                            moved, position = await tracker.evaluate(
                                "tracker => [tracker.hasScrolled(), tracker.position()]"
                            )
                        except Error as error:
                            if not _scroll_context_disappeared(frame, error):
                                raise
                            continue
                        scrolled = scrolled or bool(moved)
                        positions.append(position)
                    return scrolled, positions

                scrolled = await _scroll_ended(read)
                if not scrolled:
                    # The wheel goes where the mouse is: outside the page's scroll container (when the document does
                    # not scroll itself), it moves nothing. It is then sent over the largest one in view.
                    point = await _scroll_container_point(window, delta)
                    if point is not None:
                        await window.page.mouse.move(*point)
                        await window.page.mouse.wheel(delta_x=0, delta_y=delta)
                        scrolled = await _scroll_ended(read)
                if not scrolled:
                    logger.info("🪦 Scroll action did not move the page or a scroll container. Failing action...")
                    raise ScrollActionFailedError()
            finally:
                for _, tracker in trackers:
                    # Navigation or frame removal can destroy the JS context.
                    with suppress(Error):
                        await tracker.evaluate("tracker => tracker.dispose()")
                    with suppress(Error):
                        await tracker.dispose()
        case _:
            raise ValueError(f"Unsupported action type: {type(action)}")
    return True


@profiler.profiled("BrowserController.execute_interaction_action", service_name="execution")
async def execute_interaction_action(
    window: BrowserWindow,
    action: InteractionAction,
    prev_snapshot: BrowserSnapshot | None = None,
    *,
    storage: BaseStorage | None = None,
    verbose: bool = False,
) -> bool:
    """Interact with an element within `action.timeout`.

    The timeout covers locating the element and the interaction itself, fallbacks included.
    The page's reaction (a navigation it started) is waited for by `execute`, best-effort.
    """
    if action.selectors is None:
        raise ValueError(f"Selector is required for {action.name()}")
    deadline = asyncio.get_running_loop().time() + action.timeout / 1000
    scope = asyncio.timeout_at(deadline)
    try:
        async with scope:
            await _interact(window, action, _ActionBudget(deadline), prev_snapshot, storage=storage, verbose=verbose)
    except TimeoutError as e:
        if not scope.expired():
            raise
        raise NotteTimeoutError(message=f"Action timed out after {action.timeout}ms") from e
    return True


async def _locate(window: BrowserWindow, action: InteractionAction, snapshot: BrowserSnapshot | None) -> Locator:
    """Locates the element of an action. The CSS and XPath selectors of an observed element are paths from the
    root of the page: when part of the page re-renders after it was observed (a list of results updating), they
    can match nothing. The element is then found again in the current page by what it is (see `_find_again`)."""
    assert action.selectors is not None
    try:
        return await locate_element(window.page, action.selectors)
    except InvalidLocatorRuntimeError:
        observed = _observed_node(action, snapshot)
        # on another page, an element with the same identity is not the observed one
        if observed is None or snapshot is None or snapshot.metadata.url != window.page.url:
            raise
        selectors = await _find_again(window, observed, snapshot)
        if selectors is None:
            raise
        logger.info(f"Element {action.id} moved since it was observed: found again by its role, name and text")
        return await locate_element(window.page, selectors)


def _observed_node(action: InteractionAction, snapshot: BrowserSnapshot | None) -> DomNode | None:
    """The observed node an action targets, when it was located with that node's selectors (an empty XPath is
    the default of selectors given as a dict)."""
    if snapshot is None or action.selectors is None:
        return None
    node = snapshot.dom_node.interaction_nodes_by_id.get(action.id)
    if node is None or node.computed_attributes.selectors is None:
        return None
    observed = node.computed_attributes.selectors
    xpaths = {"", observed.xpath_selector}
    if observed.in_shadow_root:
        # resolution rewrites the XPath of a node in a shadow root
        xpaths.add(selectors_through_shadow_dom(node).xpath_selector)
    given = action.selectors
    if (observed.css_selector, observed.iframe_parent_css_selectors) != (
        given.css_selector,
        given.iframe_parent_css_selectors,
    ) or given.xpath_selector not in xpaths:
        # the action was given selectors of its own
        return None
    return node


def _identity(node: DomNode) -> tuple[str, str, str, str, str, tuple[str, ...]]:
    tag_name = node.attributes.tag_name if node.attributes is not None else ""
    href = (node.attributes.href if node.attributes is not None else None) or ""
    name = " ".join((node.accessible_name or "").split())
    # the element is looked for in its own frame only
    selectors = node.computed_attributes.selectors
    frame = tuple(selectors.iframe_parent_css_selectors) if selectors is not None else ()
    return tag_name, node.get_role_str(), name, " ".join(node.inner_text().split()), href, frame


async def _find_again(window: BrowserWindow, observed: DomNode, snapshot: BrowserSnapshot) -> NodeSelectors | None:
    """The selectors of the one interaction node of the current page with the observed node's tag, role,
    accessible name, text, link and frame. None when there is no such node or more than one, or when the observed
    page already had several (two "Delete" buttons): the element is not guessed."""
    identity = _identity(observed)
    if len(identity[2]) == 0 and len(identity[3]) == 0:
        return None
    if sum(_identity(node) == identity for node in snapshot.dom_node.interaction_nodes()) != 1:
        return None
    try:
        dom = await parse_dom(window.page)
    except (Error, SnapshotProcessingError) as e:
        logger.debug(f"Could not read the page to find element {observed.id} again: {type(e).__name__}")
        return None
    matches = [node for node in dom.interaction_nodes() if _identity(node) == identity]
    if len(matches) != 1:
        return None
    return await resolve_selectors(matches[0])


async def _interact(
    window: BrowserWindow,
    action: InteractionAction,
    budget: _ActionBudget,
    prev_snapshot: BrowserSnapshot | None,
    *,
    storage: BaseStorage | None = None,
    verbose: bool = False,
) -> None:
    assert action.selectors is not None
    # locate element (possibly in iframe)
    locator: Locator = await _locate(window, action, prev_snapshot)

    match action:
        # Interaction actions
        case ClickAction():
            is_disabled = await locator.evaluate(
                _IS_DISABLED,
                timeout=budget.remaining_ms(),
            )
            if is_disabled:
                raise ActionExecutionError(action.id, window.page.url, reason="Element is disabled")
            # an image-map `<area>` has no box, so Playwright never finds it visible: its own click follows its link
            if await locator.evaluate("(el) => el.localName === 'area'", timeout=budget.remaining_ms()):
                await locator.evaluate("(el) => el.click()", timeout=budget.remaining_ms())
            else:
                try:
                    # hold back part of the budget for the JS click fallback
                    await locator.click(timeout=budget.remaining_ms(keep_ms=action.timeout / 5))
                except PlaywrightTimeoutError as e:
                    logger.warning(f"Failed to click on element: {e}, fallback to js click")
                    await locator.evaluate("(el) => el.click()", timeout=budget.remaining_ms())

        case FillAction(value=value):
            slider = await locator.evaluate(_SLIDER_VALUE, timeout=budget.remaining_ms())
            if slider is not None:
                await _move_slider(window, locator, get_str_value(value), slider, budget)
            elif text_contains_tabs(text=get_str_value(value)):
                if verbose:
                    logger.info(
                        "🪦 Indentation detected in fill action: simulating clipboard copy/paste for better string formatting"
                    )
                await locator.focus(timeout=budget.remaining_ms())

                if action.clear_before_fill:
                    await _clear_focused_field(window)
                else:
                    await locator.evaluate(_MOVE_CARET_TO_END, timeout=budget.remaining_ms())

                # Use isolated clipboard variable instead of system clipboard
                await window.page.evaluate(
                    _PASTE_TEXT,
                    get_str_value(value),
                )

                await window.short_wait()
            elif action.clear_before_fill:
                # `fill` replaces the current value. `force` (skip actionability checks) is what every
                # default fill used before `clear_before_fill` stopped being passed as `force`.
                await locator.fill(get_str_value(value), timeout=budget.remaining_ms(), force=True)
            else:
                await _append_text(window, locator, get_str_value(value), budget.remaining_ms())
        case MultiFactorFillAction(value=value):
            # click the locator, then fill in one number at a time
            await locator.click(timeout=budget.remaining_ms())
            if action.clear_before_fill:
                await _clear_focused_field(window)

            for num in get_str_value(value):
                await window.page.keyboard.press(key=num)
                await window.page.wait_for_timeout(100)
        case FallbackFillAction(value=value):
            await locator.click(timeout=budget.remaining_ms())
            if action.clear_before_fill:
                await _clear_focused_field(window)
            else:
                await locator.evaluate(_MOVE_CARET_TO_END, timeout=budget.remaining_ms())
            await locator.press_sequentially(get_str_value(value), delay=100, timeout=budget.remaining_ms())
            await window.short_wait()
        case CheckAction(value=value):
            if value:
                await locator.check(timeout=budget.remaining_ms())
            else:
                await locator.uncheck(timeout=budget.remaining_ms())
        case SelectDropdownOptionAction(value=value):
            # Check if it's a standard HTML select
            tag_name: str = await locator.evaluate("el => el.tagName.toLowerCase()", timeout=budget.remaining_ms())
            if tag_name == "select":
                # Handle standard HTML select
                _ = await locator.select_option(get_str_value(value), timeout=budget.remaining_ms())
            else:
                await _select_custom_dropdown_option(window, locator, get_str_value(value), budget)
        case UploadFileAction():
            if await upload_file(
                window,
                locator,
                action,
                budget.remaining_ms,
                prev_snapshot,
                storage=storage,
                verbose=verbose,
            ):
                return
        case DownloadFileAction():
            await download_file(window, locator, action, budget.remaining_ms, storage=storage)
        case _:
            raise ValueError(f"Unsupported action type: {type(action)}")
    if action.press_enter:
        if verbose:
            logger.info(f"🪦 Pressing enter for action {action.id}")
        await window.short_wait()
        await window.page.keyboard.press("Enter")


@profiler.profiled("BrowserController.execute", service_name="execution")
@capture_playwright_errors()
async def execute(
    window: BrowserWindow,
    action: BaseAction,
    *,
    prev_snapshot: BrowserSnapshot | None = None,
    storage: BaseStorage | None = None,
    verbose: bool = False,
) -> bool:
    if not isinstance(action, ClickAction):
        return await _execute(window, action, prev_snapshot=prev_snapshot, storage=storage, verbose=verbose)
    # A click that opens a file chooser chooses no file: it fails. The page records the clicks that reach a file input
    # (Playwright reports the chooser after the click has returned); the chooser is intercepted, so that no native
    # dialog stays open.
    page = window.page
    choosers: list[FileChooser] = []

    def on_chooser(chooser: FileChooser) -> None:
        choosers.append(chooser)

    clicks: JSHandle | None = None
    page.on("filechooser", on_chooser)
    try:
        try:
            clicks = await page.evaluate_handle(_FILE_INPUT_CLICKS)
        except Error:
            # navigating already: only the chooser is seen
            pass
        retval = await _execute(window, action, prev_snapshot=prev_snapshot, storage=storage, verbose=verbose)
        opened = len(choosers) > 0
        if retval and not opened and clicks is not None:
            with suppress(Error):  # the click navigated away
                opened = bool(await clicks.evaluate("clicks => clicks.opened()"))
    finally:
        page.remove_listener("filechooser", on_chooser)
        if clicks is not None:
            with suppress(Error):
                await clicks.evaluate("clicks => clicks.dispose()")
            with suppress(Error):
                await clicks.dispose()
    if retval and opened:
        raise FileChooserOpenedError()
    return retval


async def _execute(
    window: BrowserWindow,
    action: BaseAction,
    *,
    prev_snapshot: BrowserSnapshot | None,
    storage: BaseStorage | None,
    verbose: bool,
) -> bool:
    """Execute `action`, then wait until the page has reacted to it (`notte_browser.settle`): a navigation it started
    has rendered or loaded, a new tab it opened (after a click, a goto or a key press) is switched to and waited for.
    """
    page = window.page
    context = page.context
    tabs = list(context.pages)
    url = page.url
    # a tab opened once the settle is over is switched to by the next observation
    await window.watch_new_tabs(_can_create_tab(action))
    # tracked from right before the action
    settle = (
        await PageSettle.start(
            page,
            tabs=_can_create_tab(action),
            timeout_ms=LONG_GRACE_MS if isinstance(action, GotoAction) else None,
        )
        if _settles(action)
        else None
    )
    retval = True
    closed_during_click: Error | None = None
    try:
        match action:
            case InteractionAction():
                try:
                    retval = await execute_interaction_action(
                        window, action, prev_snapshot, storage=storage, verbose=verbose
                    )
                except Error as error:
                    # A click handler can close its own tab before the driver acknowledges the click. Continue
                    # only if the action produces a live replacement; otherwise preserve the original error.
                    if (
                        not isinstance(action, ClickAction)
                        or not page.is_closed()
                        or "Target page, context or browser has been closed" not in str(error)
                    ):
                        raise
                    closed_during_click = error
            case CompletionAction(success=success, answer=answer):
                if verbose:
                    logger.info(
                        f"Completion action: status={'success' if success else 'failure'} with success = {success}, answer = {answer}"
                    )
            case EvaluateJsAction():
                if verbose:
                    logger.error("EvaluateJs action should not be executed inside the controller")
            case HelpAction():
                if verbose:
                    logger.error("Help action should not be executed inside the controller")
                retval = False
            case BrowserAction():
                retval = await execute_browser_action(window, action, verbose=verbose)
            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")
        if settle is not None:
            if not isinstance(action, GotoAction):
                settle.acted()
            # a goto's budget counts from its start: its commit and the wait for its page share `timeout_goto_ms`
            if retval:
                # A navigation response confirms a new document; equivalent hash-route URLs return None.
                # An exact-URL no-op keeps the previous response, so exclude it before consulting the response.
                new_document = isinstance(action, GotoAction) and action.url != url and window.goto_response is not None
                await _settle(settle, action, url, verbose=verbose, new_document=new_document)
        if closed_during_click is not None and not any(
            tab not in tabs and not tab.is_closed() for tab in context.pages
        ):
            raise closed_during_click
        if isinstance(action, (GotoAction, GotoNewTabAction)) and settle is None:
            # a goto that is not settled keeps the fixed wait before the new-tab check, which callers that observe
            # right after it rely on (a page its scripts render after its load)
            await window.short_wait()
        # Only check for new tabs if the action can potentially create one
        # a tab can open while another closes: the count does not change
        opened = any(tab not in tabs for tab in context.pages)
        if _can_create_tab(action) and (len(context.pages) != len(tabs) or opened) and len(context.pages) > 0:
            last = context.pages[-1]
            # Selection can happen automatically when the opener closes. Readiness is independent of selection.
            # A goto_new_tab already loaded its own new page.
            if last not in tabs and not isinstance(action, GotoNewTabAction):
                tab = settle.tab(last) if settle is not None else PageSettle(last, None, tabs=False)
                try:
                    await tab.wait(document="requests")
                finally:
                    await tab.close()
            if last is not window.page:
                if verbose:
                    id_str = f" id={action.id}" if isinstance(action, InteractionAction) else ""
                    logger.info(f"🪦 Action {action.type}{id_str} resulted in a new tab, switched to it...")
                # A target=_blank download can briefly create a page that closes once the download starts.
                if not last.is_closed():
                    try:
                        await last.bring_to_front()
                    except Error:
                        if not last.is_closed():
                            raise
                    else:
                        window.page = last
    finally:
        if settle is not None:
            await settle.close()
        if window.page is not page:
            # the action's tab is acted on already
            await window.watch_new_tabs(False)
    return retval
