// Focus the editing host of an element inside an editable region (a paragraph of a `contenteditable` body), so the
// text typed next goes to it. The paragraph cannot take focus itself: Playwright's `fill` and `focus` on it leave
// the focus where it was, and in a frame (a TinyMCE or CKEditor 4 iframe) the keyboard then types into the page.
// Returns whether the element is part of a larger editing host: clearing it must then not select the whole host.
(el) => {
    if (!el.isContentEditable) return false;
    let host = el;
    while (host.parentElement !== null && host.parentElement.isContentEditable) host = host.parentElement;
    if (host === el) return false;
    host.focus();
    return true;
}
