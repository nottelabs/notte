// Inner scroll boxes do not change the document's viewport dimensions. Read their
// available directions for act(), without changing how scroll actions are executed.
() => {
    const directions = new Set();
    const roots = [document];
    // A form's named controls can hide its own DOM properties and methods.
    const getter = (prototype, name) => {
        const get = Object.getOwnPropertyDescriptor(prototype, name).get;
        return el => get.call(el);
    };
    const parentElement = getter(Node.prototype, 'parentElement');
    const shadowRoot = getter(Element.prototype, 'shadowRoot');
    const scrollHeight = getter(Element.prototype, 'scrollHeight');
    const clientHeight = getter(Element.prototype, 'clientHeight');
    const scrollTop = getter(Element.prototype, 'scrollTop');
    const scrollingElement = getter(Document.prototype, 'scrollingElement')(document);
    const bounds = el => Element.prototype.getBoundingClientRect.call(el);
    const parent = el => {
        const root = Node.prototype.getRootNode.call(el);
        return parentElement(el) || (root instanceof ShadowRoot ? root.host : null);
    };
    const clips = value => /^(auto|scroll|overlay|hidden|clip)$/.test(value);
    const visible = el => {
        if (!Element.prototype.checkVisibility.call(el, {checkOpacity: true, checkVisibilityCSS: true})) return false;
        const rect = bounds(el);
        let left = Math.max(0, rect.left), right = Math.min(innerWidth, rect.right);
        let top = Math.max(0, rect.top), bottom = Math.min(innerHeight, rect.bottom);
        for (let ancestor = parent(el); ancestor; ancestor = parent(ancestor)) {
            const style = getComputedStyle(ancestor);
            if (Number(style.opacity) === 0) return false;
            const box = bounds(ancestor);
            if (clips(style.overflowX)) {
                left = Math.max(left, box.left);
                right = Math.min(right, box.right);
            }
            if (clips(style.overflowY)) {
                top = Math.max(top, box.top);
                bottom = Math.min(bottom, box.bottom);
            }
        }
        if (right <= left || bottom <= top) return false;
        // Covered boxes cannot receive the wheel. Descend through open shadow hosts.
        const x = (left + right) / 2, y = (top + bottom) / 2;
        let hit = Document.prototype.elementFromPoint.call(document, x, y);
        while (hit && shadowRoot(hit)) {
            const inner = shadowRoot(hit).elementFromPoint(x, y);
            if (!inner || inner === hit) break;
            hit = inner;
        }
        for (; hit; hit = parent(hit)) if (hit === el) return true;
        return false;
    };
    for (const root of roots) {
        for (const el of root.querySelectorAll('*')) {
            if (shadowRoot(el)) roots.push(shadowRoot(el));
            if (el === scrollingElement) continue;
            const max = scrollHeight(el) - clientHeight(el);
            if (max <= 1) continue;
            const style = getComputedStyle(el);
            if (!/^(auto|scroll|overlay)$/.test(style.overflowY) || !visible(el)) continue;
            const reversed = /^(flex|inline-flex)$/.test(style.display) && style.flexDirection === 'column-reverse';
            const lower = reversed ? -max : 0, upper = reversed ? 0 : max;
            if (scrollTop(el) > lower + 1) directions.add('up');
            if (scrollTop(el) < upper - 1) directions.add('down');
        }
    }
    return Array.from(directions);
}
