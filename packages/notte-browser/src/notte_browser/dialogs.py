"""Dismiss a dialog a site opened over the page when it blocks an action (`dismiss_blocking_dialogs`).

A cookie or terms dialog, a sign-in prompt, a promo sheet or a welcome modal makes the rest of the page inert or
covers it: a fill then "stays empty", a click is refused as disabled. With the session option on, such a failure of
a click or fill on a selector the caller wrote, when it names a dialog in the way of its element, is looked at
again (`js/blocking_dialog.js`): the dialog is dismissed through its own controls and the action is retried once.
A timeout is left as it is: the action may have reached the page before it.

The controls are tried in this order, and the next one only when the dialog is still shown:

1. a close, dismiss or decline control ("Close", "×", "Dismiss sign-in info.", "No thanks", "Reject all");
2. the Escape key, unless the target is inside a popover of the page (a picker the caller opened), which Escape
   would close too;
3. an accept or acknowledge control ("Accept", "Agree", "Got it", "OK").

Closing and declining come before accepting: cookies or terms are accepted on the caller's behalf only when the
dialog offers no other way out. Several dialogs can stack (a promo sheet over a sign-in prompt): up to `MAX_DIALOGS`
are dismissed before the one retry.

What was done to each dialog is said in the action's result message (`describe`).
"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Literal

from notte_core.actions import ClickAction, FillAction, InteractionAction
from notte_core.errors import ActionExecutionError
from notte_core.logging import logger

from notte_browser.dom.locate import locate_element
from notte_browser.driver import ElementHandle, Error, JSHandle
from notte_browser.driver import TimeoutError as PlaywrightTimeoutError
from notte_browser.js import script
from notte_browser.settle import LONG_GRACE_MS, PageSettle
from notte_browser.window import BrowserWindow

_BLOCKING_DIALOG = script("blocking_dialog.js")
_IS_SHOWN = (
    "(el) => el.isConnected && el.getClientRects().length > 0 && (typeof el.checkVisibility !== 'function'"
    " || el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}))"
)

# how long the target is waited for when looked at again (it was located once already)
LOCATE_MS = 1_000
# how long a dismiss control's click waits for the control to be clickable before a script click
CLICK_MS = 2_000
# how long a dialog gets to go away (a fade-out transition) after a control was used
GONE_MS = 1_500
# how long looking at the page for a dialog may take, before the action's own failure stands
LOOK_S = 5.0
# how a failure says that a dialog is in the way of its element (`notte_browser.execution._in_the_way`)
DIALOG_IN_THE_WAY = ": a dialog covers the element"
_GONE_POLL_S = 0.1
# the most dialogs dismissed before the action is retried
MAX_DIALOGS = 3
# a dialog's label in a message: its first words
_LABEL_WORDS = 8
_LABEL_CHARS = 80

How = Literal["close", "decline", "Escape", "accept"]


def _cut(text: str) -> str:
    words = text.split()
    short = " ".join(words[:_LABEL_WORDS]) + ("..." if len(words) > _LABEL_WORDS else "")
    return short if len(short) <= _LABEL_CHARS else short[:_LABEL_CHARS].rstrip() + "..."


@dataclass
class Dismissal:
    """What was done to one dialog."""

    reason: str
    label: str
    # all the dialog's text, uncut: what a quoted label or control name is checked against (`texts`)
    text: str
    # the controls used, in order, that did not make the dialog go away: their kind and name (None for Escape)
    tried: list[tuple[How, str | None]] = field(default_factory=list)
    # how the dialog went away, and by which control (None for Escape)
    how: How | None = None
    control: str | None = None

    def texts(self) -> list[str]:
        """The page text this record's quotes come from: its label, the dialog's whole text and control names."""
        names = [name for _, name in self.tried]
        return [text for text in (self.label, self.text, self.control, *names) if text]

    def describe(self, *, quote: bool) -> str:
        """`dialog "Legal Terms" (inert target): Escape had no effect, then accepted by its accept control 'Agree'`.
        Without `quote`, no page text: the dialog and controls are not named."""
        label = f'dialog "{_cut(self.label)}"' if quote and self.label else "dialog"
        tried = [
            "Escape had no effect"
            if name is None
            else f"its {kind} control{f' {name!r}' if quote else ''} had no effect"
            for kind, name in self.tried
        ]
        done: str
        if self.how is None:
            done = "still shown"
        elif self.how == "Escape":
            done = "closed by Escape"
        else:
            verb = {"close": "closed", "decline": "declined", "accept": "accepted"}[self.how]
            control = f" {self.control!r}" if quote and self.control else ""
            done = f"{verb} by its {self.how} control{control}"
        steps = ", ".join([*tried, done])
        return f"{label} ({self.reason} target): {steps}"


def retries_after_dismissal(action: object, error: BaseException) -> bool:
    """Whether a failed action is one a blocking dialog explains: a click or fill on a selector its caller wrote (an
    observed element, with an id, is left as it is) that was refused as disabled or whose field did not keep the
    text, with a dialog found in the way of its element. A timeout is not retried: the click or the Enter key may
    have reached the page before it, and a dialog shown now can be its result."""
    if not isinstance(action, (ClickAction, FillAction)) or action.id or action.selectors is None:
        return False
    return isinstance(error, ActionExecutionError) and DIALOG_IN_THE_WAY in error.dev_message


async def _shown(dialog: ElementHandle) -> bool:
    try:
        return bool(await dialog.evaluate(_IS_SHOWN))
    except Error:
        # the document is gone: the dismissal navigated
        return False


async def _gone(dialog: ElementHandle) -> bool:
    """Whether the dialog goes away within `GONE_MS`."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + GONE_MS / 1000
    while await _shown(dialog):
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(_GONE_POLL_S)
    return True


async def _click(window: BrowserWindow, control: ElementHandle, *, pointer: bool) -> None:
    """Click a dismiss control as a user would, by script when the pointer cannot reach it, and wait for the page's
    reaction as after any click (a terms dialog's Agree can reload the page). Without `pointer`, the click is by
    script from the start: a popover of the page that holds the target (a picker the caller opened) closes on a
    pointer press outside it, and the retried action would then find no target."""
    settle = await PageSettle.start(window.page, tabs=False)
    try:
        if pointer:
            try:
                await control.click(timeout=CLICK_MS)
            except PlaywrightTimeoutError:
                await control.evaluate("(el) => el.click()")
        else:
            await control.evaluate("(el) => el.click()")
        settle.acted()
        await settle.wait(grace_ms=LONG_GRACE_MS, document="requests")
    finally:
        await settle.close()


async def _dismiss(window: BrowserWindow, found: dict[str, JSHandle]) -> Dismissal:
    dialog = found["dialog"].as_element()
    assert dialog is not None
    record = Dismissal(
        reason=str(await found["reason"].json_value()),
        label=str(await found["label"].json_value()),
        text=str(await found["text"].json_value()),
    )
    names: list[str] = await found["closeNames"].json_value()
    kinds: list[str] = await found["closeKinds"].json_value()
    closes = [found[f"close{index}"].as_element() for index in range(len(names))]
    accept = found["accept"].as_element()
    accept_name = str(await found["acceptName"].json_value())
    # a target in a popover the caller opened: no Escape, and clicks by script (see `_click`)
    in_popover = bool(await found["targetInPopover"].json_value())

    async def use(kind: How, name: str | None, control: ElementHandle | None) -> bool:
        """Use one control (Escape without one) and say whether the dialog went away. It is recorded before it is
        used, and nothing from here on raises: a control that was used is always reported, also when using it failed
        half-way (the page rebuilt the control, or is navigating)."""
        record.tried.append((kind, name))
        try:
            if control is None:
                await window.page.keyboard.press("Escape")
            else:
                await _click(window, control, pointer=not in_popover)
        except Error as e:
            logger.debug(f"Using a dialog's {kind} control failed: {type(e).__name__}")
        if not await _gone(dialog):
            return False
        _ = record.tried.pop()
        record.how, record.control = kind, name
        return True

    try:
        # every close and decline control before Escape and accepting: the first one can be a dead decoration
        for close, name, kind in zip(closes, names, kinds):
            if await use("decline" if kind == "decline" else "close", name, close):
                return record
        if not in_popover and await use("Escape", None, None):
            return record
        if accept is not None:
            _ = await use("accept", accept_name, accept)
        return record
    finally:
        for handle in (dialog, *closes, accept):
            if handle is not None:
                with suppress(Error):
                    await handle.dispose()


async def _look(window: BrowserWindow, action: InteractionAction) -> dict[str, JSHandle] | None:
    """The dialog that blocks `action`'s target and its controls (`js/blocking_dialog.js`), None without one."""
    assert action.selectors is not None
    locator = await locate_element(window.page, action.selectors, wait_ms=LOCATE_MS)
    target = await locator.element_handle(timeout=LOCATE_MS)
    try:
        frame = await target.owner_frame()
        if frame is None or frame != window.page.main_frame:
            # dialogs that block the page are in the main document
            return None
        found = await window.page.evaluate_handle(_BLOCKING_DIALOG, target)
    finally:
        with suppress(Error):
            await target.dispose()
    try:
        if await found.evaluate("(found) => found === null"):
            return None
        return await found.get_properties()
    finally:
        with suppress(Error):
            await found.dispose()


async def dismiss_blocking_dialogs(window: BrowserWindow, action: InteractionAction) -> list[Dismissal]:
    """Dismiss the dialogs that block `action`'s target, up to `MAX_DIALOGS`. Returns what was done to each; an empty
    list when nothing blocks the target the way a dialog does (the failure has another cause), a list whose last
    dismissal has no `how` when a dialog could not be dismissed.

    Looking at the page is bounded by `LOOK_S` and nothing is used when it fails. Once a control of a dialog is
    used, that dialog's dismissal runs to its end, so that what was used is always returned."""
    done: list[Dismissal] = []
    for _ in range(MAX_DIALOGS):
        try:
            async with asyncio.timeout(LOOK_S):
                found = await _look(window, action)
        except Exception as e:  # the target is gone, or the page went away or does not answer: nothing to look at
            logger.debug(f"The target of the failed action could not be looked at again: {type(e).__name__}")
            return done
        if found is None:
            return done
        try:
            record = await _dismiss(window, found)
        except Error as e:  # the dialog could not be read: nothing of it was used
            logger.debug(f"The dialog blocking the failed action could not be read: {type(e).__name__}")
            return done
        finally:
            for handle in found.values():
                with suppress(Error):
                    await handle.dispose()
        done.append(record)
        if record.how is None:
            return done
    return done
