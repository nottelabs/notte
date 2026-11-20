// What is in the way of an action on `el`, for the message of an action that failed: the element the page shows at
// its center when that is another element (a dialog over it, a banner), or the inert ancestor that keeps it from
// taking input (a page made inert behind a modal dialog). Null when nothing is found in the way.
//
// A dialog is a `<dialog>` or an element with role dialog, alertdialog or aria-modal, shown: the one over the
// element, or the one in the wrapper over it (a wrapper that holds a dialog and its backdrop is what the hit test
// returns), or, for an inert element, the shown dialog outside the inert part. It is named by its aria-label, its
// labelling elements, its first heading or its first words.
(el, point) => {
    const DIALOG = 'dialog, [role="dialog"], [role="alertdialog"], [aria-modal="true"]';
    const MAX_WORDS = 8;
    const MAX_CHARS = 80;
    const clean = (text) => (text || "").replace(/\s+/g, " ").trim();
    const cut = (text) => {
        const words = text.split(" ");
        const short = words.length > MAX_WORDS ? words.slice(0, MAX_WORDS).join(" ") + "..." : text;
        return short.length > MAX_CHARS ? short.slice(0, MAX_CHARS).trimEnd() + "..." : short;
    };
    const shown = (node) => {
        const rect = node.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && getComputedStyle(node).visibility !== "hidden";
    };
    const host = (node) => {
        const root = node.getRootNode();
        return root instanceof ShadowRoot ? root.host : null;
    };
    const parent = (node) => node.assignedSlot || node.parentElement || host(node);
    const within = (node, outer) => {
        for (let current = node; current !== null; current = parent(current)) {
            if (current === outer) {
                return true;
            }
        }
        return false;
    };
    const name = (dialog) => {
        const label = clean(dialog.getAttribute("aria-label"));
        if (label) {
            return label;
        }
        const by = dialog.getAttribute("aria-labelledby");
        if (by) {
            // the ids refer to the dialog's own tree: its shadow root, or the document
            const root = dialog.getRootNode();
            const ids = by.split(/\s+/).filter(Boolean);
            const labels = clean(ids.map((id) => root.getElementById(id)?.innerText).join(" "));
            if (labels) {
                return labels;
            }
        }
        const heading = [...dialog.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]')].find(
            (candidate) => clean(candidate.innerText),
        );
        return clean(heading ? heading.innerText : dialog.innerText);
    };
    // All the text a quoted name is taken from, uncut: the caller looks in it for what the action typed before it
    // quotes any of it (a name cut to a few words could still show the start of a typed value)
    const text = (node) => clean(`${name(node)} ${node.innerText}`);
    const dialogOf = (cover) => {
        for (let current = cover; current !== null; current = parent(current)) {
            if (current.matches(DIALOG) && shown(current) && !within(el, current)) {
                return current;
            }
        }
        return [...cover.querySelectorAll(DIALOG)].find((candidate) => shown(candidate) && !within(el, candidate)) || null;
    };

    // the element the page shows at the center of `el` when that is another element
    let cover = null;
    const rect = el.getBoundingClientRect();
    // In a parent document `el` is the iframe; inspect the target's translated point, not the frame's center.
    const x = point ? point[0] : rect.left + rect.width / 2;
    const y = point ? point[1] : rect.top + rect.height / 2;
    if (rect.width > 0 && rect.height > 0 && x >= 0 && y >= 0 && x < innerWidth && y < innerHeight) {
        let hit = el.ownerDocument.elementFromPoint(x, y);
        while (hit !== null && hit.shadowRoot) {
            const deeper = hit.shadowRoot.elementFromPoint(x, y);
            if (deeper === null || deeper === hit) {
                break;
            }
            hit = deeper;
        }
        if (hit !== null && !within(hit, el) && !within(el, hit)) {
            cover = hit;
        }
    }
    const dialog = cover === null ? null : dialogOf(cover);
    if (dialog !== null) {
        return { kind: "dialog", name: cut(name(dialog)), text: text(dialog) };
    }
    // The hit test skips an inert element and returns what is behind it, which is not in its way: the inert part is.
    // A modal dialog escapes the inertness of its ancestors, which then are not looked at.
    for (let current = el; current !== null; current = parent(current)) {
        if (current.inert === true) {
            // a modal dialog is what makes the rest of a page inert: another dialog that happens to be shown (a chat
            // panel, a sidebar) is not in the way
            const modal = (candidate) => candidate.matches(":modal") || candidate.getAttribute("aria-modal") === "true";
            const outside = [...el.ownerDocument.querySelectorAll(DIALOG)].find(
                (candidate) => shown(candidate) && modal(candidate) && !within(candidate, current) && !within(el, candidate),
            );
            return outside
                ? { kind: "dialog", name: cut(name(outside)), text: text(outside) }
                : { kind: "inert", name: "", text: "" };
        }
        if (current.matches(":modal")) {
            break;
        }
    }
    if (cover !== null) {
        const id = cover.id ? `#${cover.id}` : "";
        return {
            kind: "element",
            name: clean(`<${cover.localName}${id}> ${cut(clean(cover.innerText))}`),
            text: clean(`<${cover.localName}${id}> ${cover.innerText}`),
        };
    }
    return null;
}
