(el) => {
    // the value and range of an ARIA slider or spinbutton (`role="slider"` / `role="spinbutton"`, not a native input),
    // or null for another element
    const role = (el.getAttribute('role') || '').trim().split(/\s+/)[0].toLowerCase();
    // a native input or an editable element takes typed text: Playwright fills it
    if ((role !== 'slider' && role !== 'spinbutton') || el instanceof HTMLInputElement || el.isContentEditable) {
        return null;
    }
    const number = (name) => {
        const value = parseFloat(el.getAttribute(name) ?? '');
        return Number.isFinite(value) ? value : null;
    };
    return { now: number('aria-valuenow'), min: number('aria-valuemin'), max: number('aria-valuemax') };
}
