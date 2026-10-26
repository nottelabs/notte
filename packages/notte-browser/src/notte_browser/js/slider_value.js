(el) => {
    // the value and range of an ARIA slider (`role="slider"`, not a native range input), or null for another element
    const role = (el.getAttribute('role') || '').trim().split(/\s+/)[0].toLowerCase();
    if (role !== 'slider' || el instanceof HTMLInputElement) {
        return null;
    }
    const number = (name) => {
        const value = parseFloat(el.getAttribute(name) ?? '');
        return Number.isFinite(value) ? value : null;
    };
    return { now: number('aria-valuenow'), min: number('aria-valuemin'), max: number('aria-valuemax') };
}
