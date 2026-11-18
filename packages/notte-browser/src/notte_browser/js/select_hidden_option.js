// Select `value` in a hidden <select>, in one step: only when the select is enabled (natively and for ARIA) and has
// an enabled option whose value is `value` or whose label is `value` (whitespace collapsed, as Playwright matches
// labels). An option is disabled natively (itself or its optgroup) or by `aria-disabled="true"` on it or an ancestor,
// up through slots and shadow hosts. Replaces the selection, also on a multiple select, and fires
// input and change like a user's choice. Returns whether it selected.
(select, value) => {
    const ariaDisabled = (element) => {
        let node = element;
        while (node !== null) {
            if (node.getAttribute('aria-disabled') === 'true') {
                return true;
            }
            if (node.assignedSlot) {
                node = node.assignedSlot;
                continue;
            }
            if (node.parentElement !== null) {
                node = node.parentElement;
                continue;
            }
            const root = node.getRootNode();
            node = root instanceof ShadowRoot ? root.host : null;
        }
        return false;
    };
    if (select.matches(':disabled') || ariaDisabled(select)) {
        return false;
    }
    const normalize = (text) => text.trim().replace(/\s+/g, ' ');
    const label = normalize(value);
    const option = [...select.options].find(
        (option) =>
            (option.value === value || normalize(option.label) === label) &&
            !option.matches(':disabled') &&
            !ariaDisabled(option)
    );
    if (option === undefined) {
        return false;
    }
    // The selectedIndex setter clears every other option first; `option.selected = true` would keep them on a
    // multiple select.
    select.selectedIndex = option.index;
    select.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
}
