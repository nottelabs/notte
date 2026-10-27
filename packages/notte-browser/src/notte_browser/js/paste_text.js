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
    // the focused element of the element's own root: in a shadow root, the document's active element is its host
    (el.getRootNode().activeElement ?? el).dispatchEvent(event);
    // a synthetic paste event inserts nothing by itself. The browser keeps a tab where the editor keeps white space
    // (`white-space: pre-wrap`, as code editors do), else inserts a non-breaking space, as when the tab is typed
    if (!event.defaultPrevented) doc.execCommand('insertText', false, text);
}
