// Select the element's own contents, so the text inserted next replaces them and nothing else of its editing host.
(el) => {
    const selection = el.ownerDocument.getSelection();
    if (selection === null) return;
    const range = el.ownerDocument.createRange();
    range.selectNodeContents(el);
    selection.removeAllRanges();
    selection.addRange(range);
}
