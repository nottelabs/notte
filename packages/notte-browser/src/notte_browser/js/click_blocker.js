// Whether a pointer click on `el` can land right now, by the checks Playwright's click retries until its timeout
// (`notte_browser.execution`, `_pointer_click`): the element has a box and is not `visibility: hidden`, part of one of
// its boxes is in the viewport, and the element at the center of that part is the element itself, or the button or
// link around it (Playwright retargets the hit test the same way). `probe.check()` says why the click cannot land
// (`hidden`, `outside`, `covered`), or `detached` once the element left the document, and for how long the answer,
// the covering element and the boxes have stayed the same: a cover that moves or changes is not a lasting one.
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
            if ((right - left) * (bottom - top) > 0.99) return { x: (left + right) / 2, y: (top + bottom) / 2 };
        }
        return null;
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
    const look = () => {
        if (!el.isConnected) return { reason: 'detached', blocker: null, boxes: '' };
        const rect = el.getBoundingClientRect();
        const boxes = box(el);
        if (rect.width <= 0 || rect.height <= 0 || getComputedStyle(el).visibility === 'hidden') {
            return { reason: 'hidden', blocker: null, boxes };
        }
        const p = point();
        if (p === null) return { reason: 'outside', blocker: null, boxes };
        const wanted = target();
        const node = hit(p.x, p.y);
        for (let n = node; n; n = parent(n)) {
            if (n === wanted) return { reason: 'ok', blocker: null, boxes };
        }
        return { reason: 'covered', blocker: node, boxes: node ? `${boxes};${box(node)}` : boxes };
    };
    let previous = null;
    let sameSince = 0;
    return {
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
