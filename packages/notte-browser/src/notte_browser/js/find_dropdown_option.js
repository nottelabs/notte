// Finds the option of an opened custom dropdown whose visible text, `data-value`
// or `value` is the requested value. When the dropdown names its list with
// aria-controls/aria-owns, only that list is searched, so a missing option is an
// error rather than a click on an unrelated item elsewhere on the page. Otherwise
// options inside the dropdown and its closest ancestors come first, then any in
// the document (popups are often portaled to <body>). ARIA options win over plain
// list items at every distance.
(el, value) => {
    const norm = (text) => (text || "").replace(/\s+/g, " ").trim();
    const wanted = norm(value);
    const root = el.getRootNode();
    const scopes = [];
    for (const attr of ["aria-controls", "aria-owns"]) {
        for (const id of (el.getAttribute(attr) || "").split(/\s+/).filter(Boolean)) {
            const owned = root.getElementById ? root.getElementById(id) : document.getElementById(id);
            if (owned) scopes.push(owned);
        }
    }
    if (scopes.length === 0) {
        for (let node = el; node; node = node.parentElement) scopes.push(node);
        scopes.push(root);
    }
    const visible = (node) => {
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
    };
    const matches = (node) =>
        node !== el &&
        visible(node) &&
        (norm(node.innerText) === wanted ||
            node.getAttribute("data-value") === value ||
            node.getAttribute("value") === value);
    for (const selector of ['[role="option"], [role="menuitemradio"], [role="menuitem"]', "li"]) {
        for (const scope of scopes) {
            for (const node of scope.querySelectorAll(selector)) {
                if (matches(node)) return node;
            }
        }
    }
    return null;
}
