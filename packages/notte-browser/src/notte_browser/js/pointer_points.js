// Which viewport points the pointer can rest on without hovering a control, and whether a wheel at the first
// one scrolls the document. With no points, it gives the viewport size only.
(points) => {
    const controls = [
        "a[href]", "area", "button", "input", "select", "textarea", "label", "summary", "option", "details",
        "video", "audio", "canvas", "iframe", "frame", "embed", "object", "[onclick]", "[tabindex]",
        "[contenteditable]:not([contenteditable=false])", "[draggable=true]",
        "[role=button]", "[role=link]", "[role=menuitem]", "[role=tab]", "[role=option]", "[role=checkbox]",
        "[role=radio]", "[role=switch]", "[role=slider]", "[role=combobox]", "[role=textbox]", "[role=menu]",
        "[role=listbox]", "[role=application]",
    ].join(",");
    const parentOf = (element) => {
        if (element.parentElement) return element.parentElement;
        const root = element.getRootNode();
        return root instanceof ShadowRoot ? root.host : null;
    };
    const at = (x, y) => {
        let element = document.elementFromPoint(x, y);
        while (element && element.shadowRoot) {
            const inner = element.shadowRoot.elementFromPoint(x, y);
            if (!inner || inner === element) break;
            element = inner;
        }
        return element;
    };
    const verdicts = new Map();
    const safe = (element) => {
        if (!element) return false;
        if (verdicts.has(element)) return verdicts.get(element);
        let verdict = true;
        try {
            if (element.matches(controls) || getComputedStyle(element).cursor === "pointer") verdict = false;
            else {
                const parent = parentOf(element);
                verdict = parent === null ? true : safe(parent);
            }
        } catch (error) {
            verdict = false;
        }
        verdicts.set(element, verdict);
        return verdict;
    };
    const scrollsDocument = (element) => {
        const root = document.scrollingElement || document.documentElement;
        if (!root || root.scrollHeight <= window.innerHeight) return false;
        for (let current = element; current; current = parentOf(current)) {
            if (current === root || current === document.body || current === document.documentElement) break;
            const style = getComputedStyle(current);
            if (/(auto|scroll|overlay)/.test(style.overflowY) && current.scrollHeight > current.clientHeight) {
                return false;
            }
        }
        return true;
    };
    const elements = points.map(([x, y]) => at(x, y));
    const first = elements.length > 0 ? elements[0] : null;
    return {
        width: window.innerWidth,
        height: window.innerHeight,
        safe: elements.map(safe),
        wheel: first !== null && safe(first) && scrollsDocument(first),
    };
}
