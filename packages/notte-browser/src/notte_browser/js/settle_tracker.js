// Tracks what changes on the page from now on (`notte_browser.settle`, which puts js/nested_roots.js and
// js/watch_url.js in place of the two capitalized names). `tracker.state()` returns the times (ms since the tracker
// started) of the first and last change, of the last DOM change and of the last URL change (`currententrychange`
// fires within `pushState`, before the mutations of a render in the same task are reported), and of the last user
// input (a trusted pointerdown or keydown: the action itself), which resets the changes: what the page did while the
// action waited for its element is not what the action did.
() => {
    const roots = NESTED_ROOTS;
    const t0 = performance.now();
    const now = () => performance.now() - t0;
    const tracker = { first: null, last: null, dom: null, urlAt: null, inputAt: null, url: location.href };
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
    // at most as many roots as js/nested_roots.js finds
    const watched = new Set();
    const frames = new Set();
    const watch = (root) => {
        if (watched.has(root) || watched.size >= 50) return;
        watched.add(root);
        observer.observe(root, { subtree: true, childList: true, characterData: true, attributes: true });
    };
    // a root found while tracking is watched, and so are the roots already in it
    const discover = (root) => {
        if (watched.has(root)) return;
        watch(root);
        for (const el of root.querySelectorAll("*")) watchWithin(el, false);
    };
    // the open shadow roots and same-origin frame documents in `element` (and its descendants with `deep`) are
    // watched too, and the next document of a frame once it has loaded
    const watchWithin = (element, deep = true) => {
        for (const el of deep ? [element, ...element.querySelectorAll("*")] : [element]) {
            if (watched.size >= 50) return;
            if (el.shadowRoot) discover(el.shadowRoot);
            if (el.tagName === "IFRAME" || el.tagName === "FRAME") {
                if (!frames.has(el)) {
                    frames.add(el);
                    el.addEventListener("load", onFrameLoad);
                }
                try { if (el.contentDocument) discover(el.contentDocument); } catch (e) {}
            }
        }
    };
    const onFrameLoad = (event) => {
        tracker.dom = changed();
        try { if (event.target.contentDocument) discover(event.target.contentDocument); } catch (e) {}
    };
    // A node whose text or attributes keep changing (a clock, a carousel, a progress counter) is not the action's
    // effect: its changes after the first two do not count. Elements added or removed always count.
    const repeats = new WeakMap();
    const counts = (mutations) => {
        const touched = new Set();
        let structural = false;
        for (const m of mutations) {
            // inline `style` changes (animations) do not count
            if (m.type === "attributes" && m.attributeName === "style") continue;
            const nodes = m.type === "childList" ? [...m.addedNodes, ...m.removedNodes] : [];
            if (nodes.some((node) => node.nodeType !== Node.TEXT_NODE)) structural = true;
            else touched.add(m.type === "characterData" ? (m.target.parentNode ?? m.target) : m.target);
        }
        let fresh = false;
        for (const node of touched) {
            const seen = (repeats.get(node) ?? 0) + 1;
            repeats.set(node, seen);
            if (seen <= 2) fresh = true;
        }
        return structural || fresh;
    };
    const observer = new MutationObserver((mutations) => {
        if (counts(mutations)) tracker.dom = changed();
        for (const m of mutations) {
            for (const node of m.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) watchWithin(node);
            }
        }
    });
    for (const root of roots) {
        watch(root);
        for (const el of root.querySelectorAll("iframe, frame")) {
            if (!frames.has(el)) {
                frames.add(el);
                el.addEventListener("load", onFrameLoad);
            }
        }
    }
    const onInput = (event) => {
        if (!event.isTrusted) return;
        tracker.inputAt = now();
        tracker.first = tracker.last = tracker.dom = tracker.urlAt = null;
    };
    for (const type of ["pointerdown", "keydown"]) window.addEventListener(type, onInput, true);
    const stopUrl = (WATCH_URL)(urlChanged);
    tracker.state = () => {
        urlChanged();
        const { first, last, dom, urlAt, inputAt } = tracker;
        return { elapsed: now(), first, last, dom, urlAt, inputAt };
    };
    tracker.dispose = () => {
        observer.disconnect();
        for (const frame of frames) {
            if (frame.removeEventListener) frame.removeEventListener("load", onFrameLoad);
        }
        for (const type of ["pointerdown", "keydown"]) window.removeEventListener(type, onInput, true);
        stopUrl();
    };
    return tracker;
}
