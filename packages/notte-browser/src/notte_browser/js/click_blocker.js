// Whether a pointer click on `el` can land right now, by the checks Playwright's click retries until its timeout
// (`notte_browser.execution`, `_pointer_click`): the element has a box and is not `visibility: hidden`, part of one of
// its boxes is in the viewport, and the element at the center of that part is the element itself, or the button or
// link around it (Playwright retargets the hit test the same way). `probe.check()` says why the click cannot land
// (`hidden`, `outside`, `covered`), or `detached` once the element left the document, and for how long the answer,
// the covering element and the boxes have stayed the same: a cover that moves or changes is not a lasting one.
// `probe.watched` says whether the element's frame is one whose activity the page watches.
(el) => {
    const doc = el.ownerDocument;
    const win = doc.defaultView;
    const t0 = performance.now();
    const now = () => performance.now() - t0;
    const parent = (node) => {
        if (node.parentElement) return node.parentElement;
        const root = node.getRootNode();
        return root instanceof ShadowRoot ? root.host : null;
    };
    const box = (node) => {
        const rect = node.getBoundingClientRect();
        return [rect.left, rect.top, rect.width, rect.height].map(Math.round).join(',');
    };
    // the element the hit test must reach: a click on the text of a button or a link hits their padding too
    const target = () => {
        if (el.matches('input, textarea, select') || el.isContentEditable) return el;
        return el.closest('button, [role=button], a, [role=link]') ?? el;
    };
    // the center of the first box with a part in the viewport
    const point = () => {
        for (const rect of el.getClientRects()) {
            const left = Math.max(rect.left, 0), top = Math.max(rect.top, 0);
            const right = Math.min(rect.right, win.innerWidth), bottom = Math.min(rect.bottom, win.innerHeight);
            // a box past both edges has two negative sides: no part of it is in the viewport either
            if (right > left && bottom > top && (right - left) * (bottom - top) > 0.99) {
                return { x: (left + right) / 2, y: (top + bottom) / 2 };
            }
        }
        return null;
    };
    // whether the page watches this frame's DOM and requests (`notte_browser.settle`, `same_origin`: the page and the
    // frames it reaches through frames of its origin; about:blank and srcdoc frames have the page's origin); the
    // activity of another frame is not seen, so its cover is not given up on early. Compared by URL: the script may
    // run in a world that reads across origins
    const origin = (w) => {
        const url = new URL(w.location.href);
        return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null;
    };
    const watched = () => {
        try {
            const top = origin(win.top);
            for (let w = win; w !== w.top; w = w.parent) {
                const own = origin(w);
                if (own !== null && own !== top) return false;
            }
            return true;
        } catch (e) {
            // a frame of another origin cannot read its ancestors
            return false;
        }
    };
    // the topmost element at a point, through open shadow roots
    const hit = (x, y) => {
        let node = Document.prototype.elementFromPoint.call(doc, x, y);
        while (node && node.shadowRoot) {
            const inner = node.shadowRoot.elementFromPoint(x, y);
            if (!inner || inner === node) break;
            node = inner;
        }
        return node;
    };
    // `boxes` is what must stay the same for the answer to count as lasting: the element's own box while it is hidden
    // or out of the viewport (one that moves may be on its way in), the covering element's box while it is covered
    // (a cover that moves may be on its way out; the element shifting under a lasting cover, as images load around
    // it, changes nothing about the cover)
    const look = () => {
        if (!el.isConnected) return { reason: 'detached', blocker: null, boxes: '' };
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0 || getComputedStyle(el).visibility === 'hidden') {
            return { reason: 'hidden', blocker: null, boxes: box(el) };
        }
        const p = point();
        if (p === null) return { reason: 'outside', blocker: null, boxes: box(el) };
        const wanted = target();
        const node = hit(p.x, p.y);
        for (let n = node; n; n = parent(n)) {
            if (n === wanted) return { reason: 'ok', blocker: null, boxes: '' };
        }
        return { reason: 'covered', blocker: node, boxes: node ? box(node) : '' };
    };
    let previous = null;
    let sameSince = 0;
    return {
        element: el,
        watched: watched(),
        check: () => {
            const seen = look();
            if (
                previous === null ||
                previous.reason !== seen.reason ||
                previous.blocker !== seen.blocker ||
                previous.boxes !== seen.boxes
            ) {
                previous = seen;
                sameSince = now();
            }
            return { reason: seen.reason, same_ms: now() - sameSince };
        },
    };
}
