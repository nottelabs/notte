// Clicks `el` from a script as a pointer does: the pointer and mouse events of a click at its center, in their
// order, the focus a mousedown gives, then `click()` for the click event and the element's activation (a link
// followed, a form submitted). A plain `el.click()` fires the click event alone: a widget that opens on mousedown
// or pointerdown (a select, a menu, a combobox) does not react to it.
(el) => {
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const init = {
        bubbles: true,
        cancelable: true,
        composed: true,
        view: window,
        clientX: x,
        clientY: y,
        screenX: x,
        screenY: y,
        button: 0,
        pointerId: 1,
        pointerType: "mouse",
        isPrimary: true,
    };
    const fire = (type, Event, buttons) => el.dispatchEvent(new Event(type, { ...init, buttons }));
    fire("pointerover", PointerEvent, 0);
    fire("mouseover", MouseEvent, 0);
    const pointerdown = fire("pointerdown", PointerEvent, 1);
    const mousedown = fire("mousedown", MouseEvent, 1);
    if (pointerdown && mousedown) {
        // the default action of a mousedown: the nearest focusable element takes the focus
        let node = el;
        while (node && !(node.tabIndex >= 0 || node.matches("input, select, textarea, button, a[href], [contenteditable]"))) {
            node = node.parentElement;
        }
        if (node && node !== document.activeElement) node.focus({ preventScroll: true });
    }
    fire("pointerup", PointerEvent, 0);
    fire("mouseup", MouseEvent, 0);
    el.click();
}
