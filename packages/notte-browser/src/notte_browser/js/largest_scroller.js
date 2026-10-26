// The scroll container of this document that a wheel can reach with the largest visible area, among those that can
// still scroll by `delta` (vertically): the center of its visible part and that area, or null. Its visible part is
// clipped by the viewport, by `clip` (the part of a frame shown in its parent page) and by its clipping ancestors, and
// the element hit at its center must be inside it. Open shadow roots are searched too.
({delta, clip}) => {
    let best = null;
    const intersect = (a, b) => ({
        left: Math.max(a.left, b.left),
        top: Math.max(a.top, b.top),
        right: Math.min(a.right, b.right),
        bottom: Math.min(a.bottom, b.bottom),
    });
    const canScroll = (element, style) => {
        const max = element.scrollHeight - element.clientHeight;
        if (max <= 1) return false;
        // a reversed flex column scrolls from -max (its top) to 0 (its bottom)
        const reversed = /^(flex|inline-flex)$/.test(style.display) && style.flexDirection === 'column-reverse';
        const lower = reversed ? -max : 0;
        const upper = reversed ? 0 : max;
        return delta > 0 ? element.scrollTop < upper - 1 : element.scrollTop > lower + 1;
    };
    const visibleRect = (element) => {
        let rect = intersect(element.getBoundingClientRect(), {
            left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight,
        });
        if (clip) rect = intersect(rect, clip);
        for (let node = element.parentElement || element.getRootNode().host; node;
            node = node.parentElement || node.getRootNode().host) {
            const style = getComputedStyle(node);
            if (style.overflowX !== 'visible' || style.overflowY !== 'visible') {
                rect = intersect(rect, node.getBoundingClientRect());
            }
        }
        return rect;
    };
    const visit = (root) => {
        for (const element of root.querySelectorAll('*')) {
            if (element.shadowRoot) visit(element.shadowRoot);
            const style = getComputedStyle(element);
            if (!/^(auto|scroll|overlay)$/.test(style.overflowY) || style.visibility !== 'visible') continue;
            if (!canScroll(element, style)) continue;
            const rect = visibleRect(element);
            const width = rect.right - rect.left;
            const height = rect.bottom - rect.top;
            if (width <= 0 || height <= 0 || (best !== null && width * height <= best.area)) continue;
            const x = rect.left + width / 2;
            const y = rect.top + height / 2;
            const hit = element.getRootNode().elementFromPoint(x, y);
            if (hit === null || !element.contains(hit)) continue;
            best = {x, y, area: width * height};
        }
    };
    visit(document);
    return best;
}
