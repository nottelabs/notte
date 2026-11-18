// Select `value` in a hidden <select>, in one step: only when the select is enabled (natively and for ARIA) and has
// an enabled option (not in a disabled optgroup) whose value is `value` or whose label is `value` (whitespace
// collapsed, as Playwright matches labels). Sets it and fires input and change like a user's choice. Returns whether
// it selected.
(select, value) => {
    if (select.matches(':disabled') || select.closest('[aria-disabled="true"]') !== null) {
        return false;
    }
    const normalize = (text) => text.trim().replace(/\s+/g, ' ');
    const label = normalize(value);
    const option = [...select.options].find(
        (option) => !option.matches(':disabled') && (option.value === value || normalize(option.label) === label)
    );
    if (option === undefined) {
        return false;
    }
    option.selected = true;
    select.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
}
