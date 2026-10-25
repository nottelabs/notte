"""Wait after an action until the page has reacted to it, instead of a fixed delay.

An action's effect often lands after the browser call returns: a click re-renders part of the page or fetches
something first, a client-side navigation fetches the next page then `pushState`s and renders it, a link loads a new
document or opens a tab. A fixed delay is wasted on actions that change nothing and too short for slow responses.
Instead `PageSettle` tracks, from right before the action, the DOM changes of the page, its same-origin frames and
its open shadow roots (inline `style` changes, i.e. animations, do not count), the fetch / XHR / document requests
the page starts, its URL changes and, if asked, the tabs it opens. The page has settled (`settled`) when:
- no request started since the action is still running, and
- nothing changed for `QUIET_MS` (or the DOM has kept changing for `SETTLE_MS`: some pages never stop), and
- something changed, or the action's grace passed: an action with no visible effect costs at most its grace, and
- after a URL change within the document, the DOM changed since (the new page rendered), or `EXPECT_MS` passed;
and in any case `CAP_MS` after the action: a page that keeps a request open is left as it is.

A navigation to a new document ends the tracking of the old one. The new document is tracked from its first render
(`DOMContentLoaded`), with `GRACE_MS` for a script that renders once it is parsed, at most `timeout_goto_ms` after the
action, and waited
for as the fixed waits it replaces did (`DocumentWait`):
- `requests` (after a click, which waited for the network to go idle): until its requests are done and its DOM has
  settled, then until it has loaded. What it renders from data it fetches after its load event is waited for;
- `loaded` (after a back / forward, which waited for the load): until its DOM has settled and it has loaded;
- `rendered` (after a key press, which waited 500 ms): until its DOM has settled or it has loaded, whichever comes
  first. Analytics and polling can keep requests in flight, and images loading, while the results are rendered.
A tab opened while the page settles ends the settle: the tab is waited for next (`PageSettle.tab`), its requests
tracked from when it appeared. A tab is known once its first response has arrived; from its first request, it is
waited for like a request in flight.

The grace and the caps count from the action itself: its input event in the page (a click's pointerdown, a key's
keydown), else its end (`PageSettle.acted`). A click that waits for its element to become clickable does not use
them up, and what the page did meanwhile (an overlay going away) is not taken for the click's effect. A new document that loads after it has settled (a slow image) is watched again
from its load event, which can start more requests.

`GRACE_MS` covers a reaction that starts right after the action (a re-render, a request). A click or a key press
can start its effect later (a timer, a debounced handler, a tab opened by a script): `LONG_GRACE_MS` is the fixed
wait that followed them before.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal

from notte_core.config import config

from notte_browser.driver import Error, JSHandle, Page, Request
from notte_browser.js import script

QUIET_MS = 200
SETTLE_MS = 1_000
GRACE_MS = 150
LONG_GRACE_MS = 500
EXPECT_MS = 1_500
CAP_MS = 3_000
POLL_MS = 50
# documents followed after an action (a navigation, then redirects by the page)
MAX_DOCUMENTS = 3

# How a new document is waited for (see the module docstring)
DocumentWait = Literal["requests", "loaded", "rendered"]

# Request types waited for. Images, fonts, media and beacons do not change what the page shows; websockets and event
# streams stay open.
TRACKED_REQUESTS = frozenset({"document", "fetch", "xhr"})

# Page-side implementation: js/settle_tracker.js, watching the roots of js/nested_roots.js with js/watch_url.js
NESTED_ROOTS_JS = script("nested_roots.js").strip()
WATCH_URL_JS = script("watch_url.js").strip()
SETTLE_TRACKER_JS = (
    script("settle_tracker.js").replace("NESTED_ROOTS", NESTED_ROOTS_JS).replace("WATCH_URL", WATCH_URL_JS)
)


@dataclass(frozen=True)
class SettleState:
    """What the page did since the action started (times in ms since then)."""

    elapsed_ms: float
    # the first and the last DOM change, URL change, request start or request end
    first_change_ms: float | None
    last_change_ms: float | None
    in_flight: int
    last_dom_change_ms: float | None = None
    # the last URL change within the document
    url_changed_ms: float | None = None
    # how long an action with no visible effect is waited for
    grace_ms: float = GRACE_MS


def settled(state: SettleState) -> bool:
    """The page has reacted to the action (see the module docstring)."""
    elapsed = state.elapsed_ms
    if elapsed >= CAP_MS:
        return True
    if state.in_flight > 0:
        return False
    first, last = state.first_change_ms, state.last_change_ms
    if first is None or last is None:
        if elapsed < state.grace_ms:
            return False
    elif elapsed - last < QUIET_MS and elapsed - first < SETTLE_MS:
        return False
    url, dom = state.url_changed_ms, state.last_dom_change_ms
    if url is None or (dom is not None and dom >= url):
        return True
    # the URL changed, the page did not render since
    return elapsed - url >= EXPECT_MS


class PageSettle:
    """What an action starts on `page`, tracked from right before it, until the page settles: on the same document,
    on the document it navigated to, or until a tab opens (with `tabs`)."""

    def __init__(self, page: Page, tracker: JSHandle | None, *, tabs: bool) -> None:
        self.page: Page = page
        # None: the page is between two documents, the next one is tracked
        self._tracker: JSHandle | None = tracker
        # when the action ended (the grace and the caps), and when the tracking of the current document started
        self._began: float = time.perf_counter()
        self._started: float = self._began
        self._in_flight: set[Request] = set()
        # when requests started or ended (ms since `_started`)
        self._changes: list[float] = []
        self._tabs: bool = tabs
        # the tabs opened since the action started: the page is waited for no longer. Each is tracked from then on
        self.opened: list[Page] = []
        self._opened_settles: dict[Page, PageSettle] = {}
        # a tab is opening: its first request was sent
        self._opening: bool = False
        page.on("request", self._request_started)
        page.on("requestfinished", self._request_ended)
        page.on("requestfailed", self._request_ended)
        if tabs:
            page.context.on("page", self._page_opened)
            page.context.on("request", self._context_request)

    @classmethod
    async def start(cls, page: Page, *, tabs: bool = False) -> "PageSettle":
        """Starts tracking `page`, right before an action. With `tabs`, a tab opened meanwhile ends the settle."""
        try:
            tracker = await page.evaluate_handle(SETTLE_TRACKER_JS)
        except Error:
            # navigating already: the next document is tracked
            tracker = None
        return cls(page, tracker, tabs=tabs)

    def acted(self) -> None:
        """The action has ended: the grace and the caps count from now."""
        self._began = time.perf_counter()

    def tab(self, page: Page) -> "PageSettle":
        """The settle of a tab the action opened, tracking its requests since it appeared (the caller closes it).
        Wait for it as for a click's new page: `wait(document="requests")`."""
        settle = self._opened_settles.pop(page, None)
        return settle if settle is not None else PageSettle(page, None, tabs=False)

    def _changed(self) -> None:
        self._changes.append((time.perf_counter() - self._started) * 1000)

    def _request_started(self, request: Request) -> None:
        if request.resource_type in TRACKED_REQUESTS:
            self._in_flight.add(request)
            self._changed()

    def _request_ended(self, request: Request) -> None:
        if request in self._in_flight:
            self._in_flight.discard(request)
            self._changed()

    def _page_opened(self, page: Page) -> None:
        self.opened.append(page)
        # its first scripts can start requests before it is waited for
        self._opened_settles[page] = PageSettle(page, None, tabs=False)

    def _context_request(self, request: Request) -> None:
        if not request.is_navigation_request():
            return
        try:
            _ = request.frame
        except Error:
            # a navigation issued before its frame exists: the first one of a new tab
            self._opening = True

    def _left_s(self, cap_ms: float) -> float:
        return max(cap_ms - (time.perf_counter() - self._began) * 1000, 0) / 1000

    async def _poll(self, grace_ms: float, *, requests: bool = True) -> None:
        """Until the current document settles or a tab opens. Without `requests`, on the DOM alone."""
        assert self._tracker is not None
        while not self.opened:
            page: dict[str, Any] = await self._tracker.evaluate("t => t.state()")
            # times since the action: its input event in the page, else its end when the document was tracked from
            # before it, else since the document was tracked
            shift = page["inputAt"] if page["inputAt"] is not None else max((self._began - self._started) * 1000, 0)

            def since(t: float | None) -> float | None:
                return None if t is None else t - shift

            changes = [t for t in self._changes if t >= shift] if requests else []
            firsts = [t for t in (page["first"], min(changes, default=None)) if t is not None]
            lasts = [t for t in (page["last"], max(changes, default=None)) if t is not None]
            state = SettleState(
                elapsed_ms=page["elapsed"] - shift,
                first_change_ms=since(min(firsts, default=None)),
                last_change_ms=since(max(lasts, default=None)),
                in_flight=(len(self._in_flight) if requests else 0) + (1 if self._opening else 0),
                last_dom_change_ms=since(page["dom"]),
                url_changed_ms=since(page["urlAt"]),
                grace_ms=grace_ms,
            )
            if settled(state):
                return
            await asyncio.sleep(POLL_MS / 1000)

    async def _loaded(self) -> bool:
        """Until the document has loaded; whether it had not yet."""
        # a document restored from the back-forward cache has loaded already, and fires no new load event
        if await self.page.evaluate("document.readyState") == "complete":
            return False
        await self.page.wait_for_load_state("load")
        return True

    async def _dispose_tracker(self) -> None:
        if self._tracker is None:
            return
        tracker, self._tracker = self._tracker, None
        try:
            await tracker.evaluate("t => t.dispose()")
            await tracker.dispose()
        except Error:
            # the document is gone, and the handle with it
            pass

    async def _track_document(self) -> None:
        """Tracks the current document from its first render: what was tracked before is over."""
        await self._dispose_tracker()
        if await self.page.evaluate("document.readyState") == "loading":
            await self.page.wait_for_load_state("domcontentloaded")
        self._tracker = await self.page.evaluate_handle(SETTLE_TRACKER_JS)
        self._started, self._changes = time.perf_counter(), []

    async def _new_document(self, grace_ms: float, document: DocumentWait) -> None:
        if document == "requests":
            await self._poll(grace_ms)
            if await self._loaded():
                # settled before its load event, which can start requests and renders of its own: a request its
                # handlers started is in flight already, no grace is needed for it
                await self._track_document()
                await self._poll(0)
            return
        rendered = asyncio.ensure_future(self._poll(grace_ms, requests=False))
        loaded = asyncio.ensure_future(self._loaded())
        until = asyncio.FIRST_COMPLETED if document == "rendered" else asyncio.FIRST_EXCEPTION
        try:
            done, _ = await asyncio.wait({rendered, loaded}, return_when=until)
        finally:
            for task in (rendered, loaded):
                _ = task.cancel()
            _ = await asyncio.gather(rendered, loaded, return_exceptions=True)
        for task in done:
            # a navigation again (the tracker is gone) or a closed page
            _ = task.result()

    async def wait(self, *, grace_ms: float = GRACE_MS, document: DocumentWait = "rendered") -> None:
        """Until the page settles, at most `CAP_MS` after the action started; after a navigation to a new document,
        until that document is ready as `document` says, at most `timeout_goto_ms` after the action started. Never
        raises: a page that does not settle in time is left as it is."""
        if self._tracker is not None:
            try:
                async with asyncio.timeout(self._left_s(CAP_MS)):
                    await self._poll(grace_ms)
                return
            except TimeoutError:
                return
            except Error:
                # a navigation to a new document destroyed the tracker
                pass
        for _ in range(MAX_DOCUMENTS):
            if self.opened:
                return
            try:
                async with asyncio.timeout(self._left_s(config.timeout_goto_ms)):
                    await self._track_document()
                    # the new document is the action's effect: only what a script renders right after it was parsed
                    # is waited for
                    await self._new_document(GRACE_MS, document)
                return
            except TimeoutError:
                return
            except Error:
                # navigated again (a redirect by the page), or the page closed
                if self.page.is_closed():
                    return

    async def close(self) -> None:
        for settle in self._opened_settles.values():
            await settle.close()
        self._opened_settles.clear()
        if self._tabs:
            _ = self.page.context.remove_listener("page", self._page_opened)
            _ = self.page.context.remove_listener("request", self._context_request)
        _ = self.page.remove_listener("request", self._request_started)
        _ = self.page.remove_listener("requestfinished", self._request_ended)
        _ = self.page.remove_listener("requestfailed", self._request_ended)
        await self._dispose_tracker()
