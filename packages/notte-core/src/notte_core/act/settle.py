"""The settle after an `act()` action: let the page react before it is observed again.

An action's effect often lands after the browser call returns. A combobox fetches its suggestions after
the input event; a client-side navigation fetches the next page, then `pushState`s and renders it.
Observed right away, the page is caught in between: the typed text without its suggestions (as if a value
were chosen), or the new URL with the old page's elements. The decider then acts on that page.

A fixed delay is wasted on actions that change nothing and too short for slow responses. Instead the
session tracks, from right before the action, DOM changes (inline `style` changes, i.e. animations, do not
count, as in `notte_core.act.wait`), the fetch / XHR / document requests the page starts, and URL changes.
The page is settled when:
- no request started since the action is still running, and
- nothing changed for `QUIET_MS` (or the DOM has kept changing for `SETTLE_MS`: some pages never stop), and
- something changed, or `GRACE_MS` passed: an action with no visible effect costs at most `GRACE_MS`, and
- the change the action announced came, or `EXPECT_MS` passed: after typing into an autocomplete field (a
  combobox, `aria-autocomplete`, a listbox popup), its visible suggestions changed; after a URL change in
  the same document, the DOM changed (the new page rendered);
and in any case after `CAP_MS`: a page that keeps loading is observed as it is, and the decider can WAIT.

Bounds (local Chromium on real sites): Google Flights renders a city's suggestions 90-160 ms after the
fill, with a request in flight from the first millisecond; GitHub's "Issues" tab fetches for ~560 ms, then
`pushState`s and renders until ~1.5 s, deferred requests included. `GRACE_MS` covers a reaction that
starts right after the action (a re-render, a request); a click already takes 500 ms (the session's
new-tab check), so it only costs typing and selecting that change nothing. `EXPECT_MS` is the pause after typing that let every city suggestion
through in a Google Flights diagnostic. `CAP_MS` is the WAIT's bound.

A navigation to a new document ends the tracking: the session's own load wait handles it.
"""

from dataclasses import dataclass

from notte_core.act.wait import NESTED_ROOTS_JS

QUIET_MS = 200
SETTLE_MS = 1_000
GRACE_MS = 150
EXPECT_MS = 1_500
CAP_MS = 3_000
POLL_MS = 50

# Request types the page waits on. Images, fonts, media and beacons do not change what is observed;
# websockets and event streams stay open.
TRACKED_REQUESTS = frozenset({"document", "fetch", "xhr"})

# `tracker.state(typed)` returns the times (ms since the tracker started) of the first and last change, of
# the last DOM change and of the last URL change (`currententrychange` fires within `pushState`, before the
# mutations of a render in the same task are reported), and, after typing, whether the visible suggestions
# changed (`null` unless the focused element autocompletes).
SETTLE_TRACKER_JS = """() => {
    // the page, its same-origin frames and open shadow roots: an autocomplete field can be in any of them
    const roots = NESTED_ROOTS;
    const t0 = performance.now();
    const now = () => performance.now() - t0;
    const tracker = { first: null, last: null, dom: null, urlAt: null, url: location.href };
    const deepActive = () => {
        let element = document.activeElement;
        for (;;) {
            if (element && element.shadowRoot && element.shadowRoot.activeElement) {
                element = element.shadowRoot.activeElement;
                continue;
            }
            let inner = null;
            if (element && (element.tagName === "IFRAME" || element.tagName === "FRAME")) {
                try { inner = element.contentDocument && element.contentDocument.activeElement; } catch (e) {}
            }
            if (!inner || inner === element) return element;
            element = inner;
        }
    };
    const autocompletes = (element) => {
        if (!element || element.tagName === "SELECT") return false;
        const autocomplete = element.getAttribute("aria-autocomplete");
        const popup = element.getAttribute("aria-haspopup");
        return element.getAttribute("role") === "combobox"
            || (autocomplete !== null && autocomplete !== "none")
            || popup === "listbox" || popup === "true";
    };
    const suggestions = () => roots.flatMap((root) => [...root.querySelectorAll("[role=option]")])
        .filter((option) => {
            const box = option.getBoundingClientRect();
            return box.width > 0 && box.height > 0;
        })
        .slice(0, 20)
        .map((option) => option.textContent.trim().slice(0, 80))
        .join("\\n");
    const before = suggestions();
    const changed = () => {
        const at = now();
        if (tracker.first === null) tracker.first = at;
        tracker.last = at;
        return at;
    };
    const urlChanged = () => {
        if (location.href === tracker.url) return;
        tracker.url = location.href;
        tracker.urlAt = changed();
    };
    const observer = new MutationObserver((mutations) => {
        if (mutations.some((m) => m.type !== "attributes" || m.attributeName !== "style")) tracker.dom = changed();
    });
    for (const root of roots) {
        observer.observe(root, { subtree: true, childList: true, characterData: true, attributes: true });
    }
    const navigation = window.navigation;
    if (navigation) navigation.addEventListener("currententrychange", urlChanged);
    tracker.state = (typed) => {
        urlChanged();
        const suggested = typed && autocompletes(deepActive()) ? suggestions() !== before : null;
        const { first, last, dom, urlAt } = tracker;
        return { elapsed: now(), first, last, dom, urlAt, suggested };
    };
    tracker.dispose = () => {
        observer.disconnect();
        if (navigation) navigation.removeEventListener("currententrychange", urlChanged);
    };
    return tracker;
}""".replace("NESTED_ROOTS", NESTED_ROOTS_JS)


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
    # None: not typed into an autocomplete field
    suggestions_changed: bool | None = None


def settled(state: SettleState) -> bool:
    """The page can be observed (see the module docstring)."""
    elapsed = state.elapsed_ms
    if elapsed >= CAP_MS:
        return True
    if state.in_flight > 0:
        return False
    first, last = state.first_change_ms, state.last_change_ms
    if first is None or last is None:
        if elapsed < GRACE_MS:
            return False
    elif elapsed - last < QUIET_MS and elapsed - first < SETTLE_MS:
        return False
    if state.suggestions_changed is False and elapsed < EXPECT_MS:
        return False
    url, dom = state.url_changed_ms, state.last_dom_change_ms
    if url is None or (dom is not None and dom >= url):
        return True
    # the URL changed, the page did not render since
    return elapsed - url >= EXPECT_MS
