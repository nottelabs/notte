(text) => {
    window.__isolatedClipboard = text;
    const dataTransfer = new DataTransfer();
    dataTransfer.setData('text/plain', window.__isolatedClipboard);
    document.activeElement.dispatchEvent(new ClipboardEvent('paste', {
        clipboardData: dataTransfer,
        bubbles: true,
        cancelable: true
    }));
}
