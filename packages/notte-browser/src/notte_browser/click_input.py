"""Report a click's input as it reaches the page, before a handler can close its tab.

The listener runs in an isolated world of its own and reports through a DevTools binding of that world, over a CDP
session that lives for the action. Nothing is exposed to the page, and no request is intercepted: exposing a page
function (`Page.expose_function`) would install a catch-all route with Patchright, so that every later request of
the page would wait for the driver.
"""

import asyncio
import json
from collections.abc import Callable, Iterator, Mapping
from typing import NamedTuple, NotRequired, TypeAlias, TypedDict, cast
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

_Json: TypeAlias = "str | int | float | bool | None | list[_Json] | dict[str, _Json]"
_Params: TypeAlias = dict[str, str | int | bool]


class _CdpFrame(TypedDict):
    id: str
    loaderId: str
    url: NotRequired[str]
    urlFragment: NotRequired[str]
    name: NotRequired[str]


class _CdpFrameTree(TypedDict):
    frame: _CdpFrame
    childFrames: NotRequired[list["_CdpFrameTree"]]


class _FrameTreeReply(TypedDict):
    frameTree: _CdpFrameTree


class _CreateWorldReply(TypedDict):
    executionContextId: int


class _ExceptionDetails(TypedDict):
    text: NotRequired[str]


class _RemoteObject(TypedDict):
    objectId: NotRequired[str]
    value: NotRequired[_Json]


class _EvaluateReply(TypedDict):
    result: _RemoteObject
    exceptionDetails: NotRequired[_ExceptionDetails]


class _BindingCalled(TypedDict):
    name: str
    payload: str


class _Document(NamedTuple):
    """A CDP frame's current document. Its loader id changes whenever the document is replaced, including across
    renderer processes, where an execution context id can name an unrelated context."""

    frame_id: str
    loader_id: str


class _World(NamedTuple):
    loader_id: str
    context_id: int


# Our world in each frame's current document, by page and CDP frame id. Later clicks reuse it while the frame still
# shows the document it was created in.
_WORLDS: WeakKeyDictionary[Page, dict[str, _World]] = WeakKeyDictionary()


async def _command(session: CDPSession, method: str, params: _Params | None = None) -> Mapping[str, _Json]:
    """A CDP command's reply, as JSON. Each caller narrows it to the reply type of its command."""
    return cast("Mapping[str, _Json]", await session.send(method, params))  # pyright: ignore[reportUnknownMemberType]


async def _send(session: CDPSession, method: str, params: _Params) -> None:
    _ = await _command(session, method, params)


async def _frame_tree(session: CDPSession) -> _CdpFrameTree:
    return cast(_FrameTreeReply, await _command(session, "Page.getFrameTree"))["frameTree"]


async def _create_world(session: CDPSession, frame_id: str) -> int:
    params: _Params = {"frameId": frame_id, "worldName": _WORLD}
    return cast(_CreateWorldReply, await _command(session, "Page.createIsolatedWorld", params))["executionContextId"]


def _checked(reply: _EvaluateReply) -> _RemoteObject:
    if "exceptionDetails" in reply:
        raise Error(f"Click input listener failed: {reply['exceptionDetails'].get('text', '')}")
    return reply["result"]


async def _call_function_on(session: CDPSession, object_id: str, function: str) -> _RemoteObject:
    params: _Params = {"objectId": object_id, "functionDeclaration": function}
    return _checked(cast(_EvaluateReply, await _command(session, "Runtime.callFunctionOn", params)))


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


async def _evaluate(session: CDPSession, context_id: int, expression: str, by_value: bool) -> _RemoteObject:
    params: _Params = {"expression": expression, "contextId": context_id, "returnByValue": by_value}
    return _checked(cast(_EvaluateReply, await _command(session, "Runtime.evaluate", params)))


async def _world(session: CDPSession, page: Page, document: _Document) -> int:
    """Our world in `document`, with the binding reporting to `session`. A cached world is reused only while its
    frame still shows the document it was created in: its context id means nothing in any other document."""
    worlds = _WORLDS.setdefault(page, {})
    cached = worlds.get(document.frame_id)
    if cached is not None and cached.loader_id == document.loader_id:
        try:
            await _send(session, "Runtime.addBinding", {"name": _BINDING, "executionContextId": cached.context_id})
            return cached.context_id
        except Error:
            # the document was replaced since the frame tree was read
            pass
    context_id = await _create_world(session, document.frame_id)
    await _send(session, "Runtime.addBinding", {"name": _BINDING, "executionContextId": context_id})
    worlds[document.frame_id] = _World(document.loader_id, context_id)
    return context_id


def _document(cdp_frame: _CdpFrame) -> _Document:
    return _Document(cdp_frame["id"], cdp_frame["loaderId"])


async def _documents(session: CDPSession, root: Frame, page: Page, frame: Frame) -> list[_Document]:
    """The current document of `frame` in the target of `session`, whose root frame is `root`. Frames that cannot be
    told apart (same URL, name and position) are all returned."""
    frames = list(_frames(await _frame_tree(session)))
    worlds = _WORLDS.get(page)
    if worlds is not None:
        live = {cdp_frame["id"] for cdp_frame in frames}
        for frame_id in [frame_id for frame_id in worlds if frame_id not in live]:
            del worlds[frame_id]
    if frame is root:
        return [_document(frames[0])]
    children = frames[1:]
    candidates = [
        cdp_frame
        for cdp_frame in children
        if cdp_frame.get("url", "") + cdp_frame.get("urlFragment", "") == frame.url
        and cdp_frame.get("name", "") == frame.name
    ] or children
    if len(candidates) == 1:
        return [_document(candidates[0])]
    path = cast(list[int], await frame.evaluate(_FRAME_PATH))
    matching: list[_Document] = []
    for candidate in candidates:
        document = _document(candidate)
        context_id = await _world(session, page, document)
        if (await _evaluate(session, context_id, f"({_FRAME_PATH})()", by_value=True)).get("value") == path:
            matching.append(document)
    return matching or [_document(candidate) for candidate in candidates]


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
            for document in await _documents(session, root, page, frame):
                listener = await _evaluate(session, await _world(session, page, document), expression, by_value=False)
                if "objectId" not in listener:
                    raise Error("Click input listener failed: no listener object")
                reporter._listeners.append(listener["objectId"])
        except BaseException:
            await reporter.dispose()
            raise
        return reporter

    def _binding_called(self, event: _BindingCalled) -> None:
        if event["name"] == _BINDING and event["payload"] == self._token:
            _ = asyncio.get_running_loop().call_soon(self.notify)

    def notify(self) -> None:
        self._on_input()

    async def _call(self, function: str) -> None:
        for listener in self._listeners:
            _ = await _call_function_on(self._session, listener, function)

    async def check(self) -> None:
        """Raises `Error` when the listener's document is gone (a URL change within the document keeps it)."""
        await self._call("function() {}")

    async def mark(self) -> None:
        """Report an input from the page now (a script's click emits no trusted pointer event)."""
        await self._call("function() { this.mark(); }")

    async def dispose(self) -> None:
        for listener in self._listeners:
            try:
                _ = await _call_function_on(self._session, listener, "function() { this.dispose(); }")
            except Error:
                # its document is gone
                pass
        self._listeners = []
        try:
            await self._session.detach()
        except Error:
            pass
