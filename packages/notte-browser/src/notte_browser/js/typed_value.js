// The value of a text field. `late`: read after a task, so that a mask that rewrites or reverts the value later
// than the input event (in a setTimeout) has run. Null for other elements (contenteditable, date, number...),
// whose value is not checked.
(el, late) => {
    const textTypes = ["text", "search", "tel", "url", "email", "password"];
    const isText =
        el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement && textTypes.includes(el.type));
    if (!isText) {
        return null;
    }
    if (!late) {
        return el.value;
    }
    return new Promise((resolve) => setTimeout(() => resolve(el.value), 0));
}
