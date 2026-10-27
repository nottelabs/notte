// Paste `text` at the selection of the element's document, which has the focus: as a paste event, which editors
// that handle pasting (CodeMirror, Monaco) insert themselves, else with the browser's text insertion. Runs in the
// element's frame: in an iframe editor, the page's own active element is the iframe.
(el, text) => {
    const doc = el.ownerDocument;
    window.__isolatedClipboard = text;
    const dataTransfer = new DataTransfer();
    dataTransfer.setData('text/plain', window.__isolatedClipboard);
    const event = new ClipboardEvent('paste', {
        clipboardData: dataTransfer,
        bubbles: true,
        cancelable: true
    });
    (doc.activeElement ?? el).dispatchEvent(event);
    // a synthetic paste event inserts nothing by itself
    if (!event.defaultPrevented) doc.execCommand('insertText', false, text);
}
