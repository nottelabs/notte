// The dialog a site opened over the page that blocks an action on `target`, and that dialog's own dismiss controls.
//
// Blocked means: the target is inside an `inert` subtree (a modal made the rest of the page inert), or the point at
// its center belongs to another element (a backdrop, the dialog itself). The dialog is a visible open `<dialog>`,
// `role=dialog`, `role=alertdialog` or `aria-modal=true` element that does not contain the target, the topmost one
// when several are open; without such a dialog, the fixed-position container of the element covering the target.
//
// Returns null when the target is not blocked that way. Otherwise an object with the dialog element, why the target
// is blocked, a label for the dialog, and its dismiss controls by preference: `close` (a close, dismiss or decline
// control, with `closeKind` saying which of the two) and `accept` (an accept, agree or acknowledge control). Links to
// policies and controls that sign in, register, subscribe or open settings are never candidates.
(target) => {
    const DIALOGS = 'dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]';
    const CONTROLS = 'button, [role="button"], a[href], input[type="button"], input[type="submit"], input[type="reset"]';
    const CLOSE_START = /^(close|dismiss|skip|no,? thanks|no thanks|not now|maybe later|later|decline|reject|refuse|deny)\b/;
    const CLOSE_WORD = /\b(close|dismiss)\b/;
    const DECLINE_START = /^(skip|no,? thanks|no thanks|not now|maybe later|later|decline|reject|refuse|deny)\b/;
    const CLOSE_GLYPHS = new Set(['×', '✕', '✖', '⨯', 'x', '⤫']);
    const ACCEPT = /^(accept( all)?( cookies)?|i accept|agree|i agree|yes,? i agree|got it|ok|okay|allow( all)?( cookies)?|i understand|understood|accept (and|&) close|accept (and|&) continue)[.!]?$/;
    const NEVER = /\b(sign|log ?in|login|register|subscribe|account|settings|preferences|customi[sz]e|manage|policy|terms|learn more|more info)\b/;

    const visible = (el) =>
        el instanceof Element &&
        el.getClientRects().length > 0 &&
        (typeof el.checkVisibility !== 'function' || el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }));
    const text = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const accessibleName = (el) => {
        const labelled = el.getAttribute('aria-labelledby');
        if (labelled) {
            const parts = labelled.split(/\s+/).map((id) => text(document.getElementById(id)?.textContent)).filter(Boolean);
            if (parts.length) return parts.join(' ');
        }
        const own = text(el.getAttribute('aria-label'));
        if (own) return own;
        const inner = text(el.innerText);
        if (inner) return inner;
        const value = text(el.value);
        if (value && el.tagName === 'INPUT') return value;
        const alt = el.querySelector('img[alt], svg title, [aria-label]');
        if (alt) return text(alt.getAttribute('alt') || alt.getAttribute('aria-label') || alt.textContent);
        return text(el.title);
    };
    const normalized = (name) => name.toLowerCase().replace(/[.!…]+$/, '').trim();
    const looksLikeClose = (el) =>
        /close|dismiss/i.test(
            `${el.id} ${el.getAttribute('class') || ''} ${el.getAttribute('data-dismiss') || ''} ${el.getAttribute('data-bs-dismiss') || ''}`
        );
    const disabled = (el) => el.disabled === true || el.getAttribute('aria-disabled') === 'true';

    // how the target is blocked
    let reason = null;
    let covering = null;
    if (target.closest('[inert]')) reason = 'inert';
    const box = target.getBoundingClientRect();
    if (box.width > 0 && box.height > 0) {
        const x = Math.min(Math.max(box.left + box.width / 2, 0), window.innerWidth - 1);
        const y = Math.min(Math.max(box.top + box.height / 2, 0), window.innerHeight - 1);
        const top = document.elementFromPoint(x, y);
        if (top && top !== target && !target.contains(top) && !top.contains(target)) {
            covering = top;
            if (reason === null) reason = 'covered';
        }
    }
    if (reason === null) return null;

    // the dialog: the topmost open one that does not contain the target
    const targetDialog = target.closest(DIALOGS);
    const open = [...document.querySelectorAll(DIALOGS)].filter(
        (el) => visible(el) && !el.contains(target) && !(targetDialog && targetDialog.contains(el))
    );
    let dialog = null;
    if (covering) dialog = open.find((el) => el.contains(covering)) || null;
    if (dialog === null && open.length) {
        const onTop = open.filter((el) => {
            const r = el.getBoundingClientRect();
            const hit = document.elementFromPoint(
                Math.min(Math.max(r.left + r.width / 2, 0), window.innerWidth - 1),
                Math.min(Math.max(r.top + r.height / 2, 0), window.innerHeight - 1)
            );
            return hit !== null && el.contains(hit);
        });
        dialog = (onTop.length ? onTop : open)[(onTop.length ? onTop : open).length - 1];
    }
    if (dialog === null && covering) {
        // no dialog role: the outermost fixed-position container of what covers the target
        let node = covering;
        let container = null;
        while (node && node !== document.body && node !== document.documentElement) {
            const position = getComputedStyle(node).position;
            if ((position === 'fixed' || position === 'sticky' || position === 'absolute') && !node.contains(target)) container = node;
            node = node.parentElement;
        }
        dialog = container;
    }
    if (dialog === null) return null;

    // the dialog's own dismiss controls
    let close = null;
    let closeExact = null;
    let accept = null;
    for (const el of dialog.querySelectorAll(CONTROLS)) {
        if (!visible(el) || disabled(el)) continue;
        const name = normalized(accessibleName(el));
        // a control named for closing closes ("Dismiss sign-in info." closes, whatever else it names)
        if (CLOSE_GLYPHS.has(name) || CLOSE_START.test(name)) {
            if (closeExact === null) closeExact = el;
        } else if (CLOSE_WORD.test(name)) {
            if (close === null) close = el;
        } else if (NEVER.test(name)) {
            continue;
        } else if (name === '' && el.tagName !== 'A' && looksLikeClose(el)) {
            if (close === null) close = el;
        } else if (ACCEPT.test(name)) {
            if (accept === null) accept = el;
        }
    }
    close = closeExact || close;
    const label =
        text(dialog.getAttribute('aria-label')) ||
        text(dialog.querySelector('h1, h2, h3, h4, [role="heading"]')?.innerText) ||
        text(dialog.innerText).slice(0, 60);
    const describe = (el) => `<${el.tagName.toLowerCase()}${el.id ? ` id="${el.id}"` : ''} class="${el.getAttribute('class') || ''}">`;
    return {
        dialog,
        reason,
        label,
        role: dialog.getAttribute('role') || dialog.tagName.toLowerCase(),
        // A popover the caller opened that holds the target (a currency picker whose search box is the target) closes
        // on Escape and on a pointer press outside it, as the dialog's controls are: the dismissal then avoids both.
        // A combobox is not one: its input sits in the page (a search box wrapped in `role=combobox`).
        targetInPopover: targetDialog !== null || target.closest('[role="menu"], [role="listbox"]') !== null,
        close,
        closeName: close ? accessibleName(close) || describe(close) : null,
        closeKind: close && DECLINE_START.test(normalized(accessibleName(close))) ? 'decline' : 'close',
        accept,
        acceptName: accept ? accessibleName(accept) : null,
    };
}
