import asyncio
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
from notte_core.errors import ActionExecutionError, NotteTimeoutError, SnapshotProcessingError
from notte_core.logging import logger
from notte_core.profiling import profiler
from notte_core.snapshot import BrowserSnapshot
from notte_core.storage import BaseStorage

from notte_browser.captcha import solve_captcha
from notte_browser.dom.locate import locate_element, selectors_through_shadow_dom
from notte_browser.dom.parsing import parse_dom
from notte_browser.driver import Error, Frame, JSHandle, Locator
from notte_browser.errors import (
    InvalidLocatorRuntimeError,
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

# A scroll that has not started `SCROLL_START_MS` after the wheel failed; one that started has ended once its
# position is the same `SCROLL_STABLE_MS` apart (a smooth scroll, a scroll-snap), at most `SCROLL_CAP_MS` after it.
SCROLL_START_MS = 200
SCROLL_STABLE_MS = 50
SCROLL_POLL_MS = 25
SCROLL_CAP_MS = 1_000


async def _scroll_ended(read: Callable[[], Awaitable[tuple[bool, list[object]]]]) -> bool:
    """Whether a scroll happened, once it has ended or failed to start. `read` returns whether the scroll started,
    and the positions it moves."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    last: list[object] | None = None
    stable_since = start
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

        async def read() -> tuple[bool, list[object]]:
            position = await target.evaluate("element => element.scrollTop")
            return position != before, [position]

        if not await _scroll_ended(read) and not await target.evaluate(_SCROLL_BOUNDARY, delta):
            raise ScrollActionFailedError()
    finally:
        with suppress(Error):
            await target.dispose()


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
    a navigation. A scroll waits for itself; a goto waits for the page's load."""
    return isinstance(action, (InteractionAction, PressKeyAction, GoBackAction, GoForwardAction, ReloadAction))


async def _settle(settle: PageSettle, action: BaseAction, url: str, *, verbose: bool) -> None:
    """Until the page has reacted to `action`, which ran on `url`."""
    match action:
        case ClickAction():
            # a click's new page is waited for until its requests are done (the network going idle)
            await settle.wait(grace_ms=LONG_GRACE_MS, document="requests")
        case PressKeyAction() | InteractionAction(press_enter=True):
            await settle.wait(grace_ms=LONG_GRACE_MS, document="rendered")
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
            await window.goto(url, wait_until=wait_until)
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
            await window.goto_and_wait(operation="back", wait_until="commit")
        case GoForwardAction():
            await window.goto_and_wait(operation="forward", wait_until="commit")
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
                await window.page.mouse.wheel(
                    delta_x=0, delta_y=(-amount if isinstance(action, ScrollUpAction) else amount)
                )

                async def read() -> tuple[bool, list[object]]:
                    scrolled = False
                    positions: list[object] = []
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

                if not await _scroll_ended(read):
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
            try:
                # hold back part of the budget for the JS click fallback
                await locator.click(timeout=budget.remaining_ms(keep_ms=action.timeout / 5))
            except PlaywrightTimeoutError as e:
                logger.warning(f"Failed to click on element: {e}, fallback to js click")
                await locator.evaluate("(el) => el.click()", timeout=budget.remaining_ms())

        case FillAction(value=value):
            if text_contains_tabs(text=get_str_value(value)):
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
    """Execute `action`, then wait until the page has reacted to it (`notte_browser.settle`): a navigation it started
    has rendered or loaded, a new tab it opened (after a click, a goto or a key press) is switched to and waited for.
    """
    page = window.page
    context = page.context
    tabs = list(context.pages)
    url = page.url
    # tracked from right before the action
    settle = await PageSettle.start(page, tabs=_can_create_tab(action)) if _settles(action) else None
    retval = True
    try:
        match action:
            case InteractionAction():
                retval = await execute_interaction_action(
                    window, action, prev_snapshot, storage=storage, verbose=verbose
                )
            case CompletionAction(success=success, answer=answer):
                if verbose:
                    logger.info(
                        f"Completion action: status={'success' if success else 'failure'} with success = {success}, answer = {answer}"
                    )
            case EvaluateJsAction():
                if verbose:
                    logger.error("EvaluateJs action should not be executed inside the controller")
                pass
            case HelpAction():
                if verbose:
                    logger.error("Help action should not be executed inside the controller")
                retval = False
            case BrowserAction():
                retval = await execute_browser_action(window, action, verbose=verbose)
            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")
        if settle is not None and retval:
            await _settle(settle, action, url, verbose=verbose)
    finally:
        if settle is not None:
            await settle.close()
    # Only check for new tabs if the action can potentially create one
    if _can_create_tab(action) and len(context.pages) != len(tabs) and len(context.pages) > 0:
        last = context.pages[-1]
        # a new tab from goto_new_tab is the window's page already, and loaded
        if last is not window.page:
            if verbose:
                id_str = f" id={action.id}" if isinstance(action, InteractionAction) else ""
                logger.info(f"🪦 Action {action.type}{id_str} resulted in a new tab, switched to it...")
            await last.bring_to_front()
            window.page = last
            if last not in tabs:
                await PageSettle.opened_tab(last)
    return retval
