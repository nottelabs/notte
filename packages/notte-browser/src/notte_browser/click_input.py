"""Report a click's input as it reaches the page, before a handler can close its tab.

The listener runs in an isolated world of its own and reports through a DevTools binding of that world, over a CDP
session that lives for the action. Nothing is exposed to the page, and no request is intercepted: exposing a page
function (`Page.expose_function`) would install a catch-all route with Patchright, so that every later request of
the page would wait for the driver.
"""

import asyncio
import json
from collections.abc import Callable, Iterator
from typing import Any, NotRequired, TypedDict, cast
from uuid import uuid4
from weakref import WeakKeyDictionary

from notte_browser.driver import CDPSession, Error, Frame, Page
from notte_browser.js import script

_CLICK_INPUT = script("click_input.js")
_WORLD = "notte-click-input"
_BINDING = "__notteClickInput"
# A frame's index among its parent's frames, from the top. Reads no page state.
_FRAME_PATH = """() => {
    const path = [];
    for (let w = window; w !== w.parent; w = w.parent) path.unshift(Array.prototype.indexOf.call(w.parent.frames, w));
    return path;
}"""
_PART_OF_PARENT_SESSION = "does not have a separate CDP session"

# Our world in each frame's current document, by page and CDP frame id. Later clicks reuse it; a document that was
# replaced took its world with it.
_WORLDS: WeakKeyDictionary[Page, dict[str, int]] = WeakKeyDictionary()


class _CdpFrame(TypedDict):
    id: str
    url: NotRequired[str]
    urlFragment: NotRequired[str]
    name: NotRequired[str]


class _CdpFrameTree(TypedDict):
    frame: _CdpFrame
    childFrames: NotRequired[list["_CdpFrameTree"]]


async def _send(session: CDPSession, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return cast("dict[str, Any]", await session.send(method, params))  # pyright: ignore[reportUnknownMemberType]


def _frames(tree: _CdpFrameTree) -> Iterator[_CdpFrame]:
    yield tree["frame"]
    for child in tree.get("childFrames", []):
        yield from _frames(child)


async def _session_of(page: Page, frame: Frame) -> tuple[CDPSession, Frame]:
    """A CDP session of the target that renders `frame` (an out-of-process frame has its own), and its root frame."""
    candidate = frame
    while candidate.parent_frame is not None:
        try:
            return await page.context.new_cdp_session(candidate), candidate
        except Error as error:
            if _PART_OF_PARENT_SESSION not in str(error):
                raise
        candidate = candidate.parent_frame
    return await page.context.new_cdp_session(page), page.main_frame


async def _evaluate(session: CDPSession, context_id: int, expression: str, by_value: bool) -> dict[str, Any]:
    evaluated = await _send(
        session, "Runtime.evaluate", {"expression": expression, "contextId": context_id, "returnByValue": by_value}
    )
    if "exceptionDetails" in evaluated:
        raise Error(f"Click input listener failed: {evaluated['exceptionDetails'].get('text', '')}")
    return cast("dict[str, Any]", evaluated["result"])


async def _world(session: CDPSession, page: Page, frame_id: str) -> int:
    """Our world in the current document of frame `frame_id`, with the binding reporting to `session`."""
    worlds = _WORLDS.setdefault(page, {})
    context_id = worlds.get(frame_id)
    if context_id is not None:
        try:
            _ = await _send(session, "Runtime.addBinding", {"name": _BINDING, "executionContextId": context_id})
            return context_id
        except Error:
            # the frame's document was replaced
            pass
    created = await _send(session, "Page.createIsolatedWorld", {"frameId": frame_id, "worldName": _WORLD})
    context_id = cast(int, created["executionContextId"])
    _ = await _send(session, "Runtime.addBinding", {"name": _BINDING, "executionContextId": context_id})
    worlds[frame_id] = context_id
    return context_id


async def _frame_ids(session: CDPSession, root: Frame, page: Page, frame: Frame) -> list[str]:
    """The CDP id of `frame` in the target of `session`, whose root frame is `root`. Frames that cannot be told
    apart (same URL, name and position) are all returned."""
    tree = cast(_CdpFrameTree, (await _send(session, "Page.getFrameTree"))["frameTree"])
    frames = list(_frames(tree))
    worlds = _WORLDS.get(page)
    if worlds is not None:
        live = {cdp_frame["id"] for cdp_frame in frames}
        for frame_id in [frame_id for frame_id in worlds if frame_id not in live]:
            del worlds[frame_id]
    if frame is root:
        return [frames[0]["id"]]
    children = frames[1:]
    candidates = [
        cdp_frame
        for cdp_frame in children
        if cdp_frame.get("url", "") + cdp_frame.get("urlFragment", "") == frame.url
        and cdp_frame.get("name", "") == frame.name
    ] or children
    if len(candidates) == 1:
        return [candidates[0]["id"]]
    path = await frame.evaluate(_FRAME_PATH)
    matching: list[str] = []
    for candidate in candidates:
        context_id = await _world(session, page, candidate["id"])
        if (await _evaluate(session, context_id, f"({_FRAME_PATH})()", by_value=True)).get("value") == path:
            matching.append(candidate["id"])
    return matching or [candidate["id"] for candidate in candidates]


class ClickInputReporter:
    """Calls `on_input` once a click's input reaches the document of a frame (its trusted `pointerdown`), or once
    it is `mark`ed. The report is queued like the settle's request attribution, so that events keep their protocol
    order (`notte_browser.settle`)."""

    def __init__(self, session: CDPSession, on_input: Callable[[], None]) -> None:
        self._session: CDPSession = session
        self._on_input: Callable[[], None] = on_input
        self._token: str = uuid4().hex
        self._listeners: list[str] = []

    @classmethod
    async def install(cls, page: Page, frame: Frame, on_input: Callable[[], None]) -> "ClickInputReporter":
        session, root = await _session_of(page, frame)
        reporter = cls(session, on_input)
        session.on("Runtime.bindingCalled", reporter._binding_called)
        try:
            expression = f"({_CLICK_INPUT})({json.dumps(_BINDING)}, {json.dumps(reporter._token)})"
            for frame_id in await _frame_ids(session, root, page, frame):
                listener = await _evaluate(session, await _world(session, page, frame_id), expression, by_value=False)
                reporter._listeners.append(cast(str, listener["objectId"]))
        except BaseException:
            await reporter.dispose()
            raise
        return reporter

    def _binding_called(self, event: dict[str, Any]) -> None:
        if event.get("name") == _BINDING and event.get("payload") == self._token:
            _ = asyncio.get_running_loop().call_soon(self.notify)

    def notify(self) -> None:
        self._on_input()

    async def _call(self, function: str) -> None:
        for listener in self._listeners:
            called = await _send(
                self._session, "Runtime.callFunctionOn", {"objectId": listener, "functionDeclaration": function}
            )
            if "exceptionDetails" in called:
                raise Error(f"Click input listener failed: {called['exceptionDetails'].get('text', '')}")

    async def check(self) -> None:
        """Raises `Error` when the listener's document is gone (a URL change within the document keeps it)."""
        await self._call("function() {}")

    async def mark(self) -> None:
        """Report an input from the page now (a script's click emits no trusted pointer event)."""
        await self._call("function() { this.mark(); }")

    async def dispose(self) -> None:
        for listener in self._listeners:
            try:
                _ = await _send(
                    self._session,
                    "Runtime.callFunctionOn",
                    {"objectId": listener, "functionDeclaration": "function() { this.dispose(); }"},
                )
            except Error:
                # its document is gone
                pass
        self._listeners = []
        try:
            await self._session.detach()
        except Error:
            pass
