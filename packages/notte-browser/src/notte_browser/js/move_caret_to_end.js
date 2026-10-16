// Put the caret at the end of the element's text so typed or pasted text is appended.
// Inputs without a selection API (e.g. type=email) keep the browser's caret placement.
(el) => {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
        try {
            el.setSelectionRange(el.value.length, el.value.length);
        } catch {}
        return;
    }
    const selection = el.ownerDocument.getSelection();
    if (selection === null) {
        return;
    }
    const range = el.ownerDocument.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
}
