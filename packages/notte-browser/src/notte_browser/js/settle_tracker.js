// Tracks what changes on the page from now on (`notte_browser.settle`, which puts js/nested_roots.js and
// js/watch_url.js in place of the two capitalized names). `tracker.state()` returns the times (ms since the tracker
// started) of the first and last change, of the last DOM change and of the last URL change (`currententrychange`
// fires within `pushState`, before the mutations of a render in the same task are reported).
() => {
    const roots = NESTED_ROOTS;
    const t0 = performance.now();
    const now = () => performance.now() - t0;
    const tracker = { first: null, last: null, dom: null, urlAt: null, url: location.href };
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
    // inline `style` changes (animations) do not count
    const observer = new MutationObserver((mutations) => {
        if (mutations.some((m) => m.type !== "attributes" || m.attributeName !== "style")) tracker.dom = changed();
    });
    for (const root of roots) {
        observer.observe(root, { subtree: true, childList: true, characterData: true, attributes: true });
    }
    const stopUrl = (WATCH_URL)(urlChanged);
    tracker.state = () => {
        urlChanged();
        const { first, last, dom, urlAt } = tracker;
        return { elapsed: now(), first, last, dom, urlAt };
    };
    tracker.dispose = () => {
        observer.disconnect();
        stopUrl();
    };
    return tracker;
}
