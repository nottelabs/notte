// The dialog a site opened over the page that blocks an action on `target`, and that dialog's own dismiss controls.
//
// Blocked means: the target is inside an `inert` subtree (a modal made the rest of the page inert), or the point at
// its center belongs to another element (a backdrop, the dialog itself). The dialog is found as `in_the_way.js` finds
// it: a visible open `<dialog>`, `role=dialog`, `role=alertdialog` or `aria-modal=true` element that does not contain
// the target and is over it (the element covering the target is in it, or is a wrapper that holds it and its
// backdrop), or, for an inert target, the modal one outside the inert part. A banner or a header over the target and
// another dialog that happens to be shown (a chat panel) are not dialogs that block it.
//
// Returns null when the target is not blocked that way. Otherwise an object with the dialog element, why the target
// is blocked, a label for the dialog, and its dismiss controls by preference: `close` (a close, dismiss or decline
// control, with `closeKind` saying which of the two) and `accept` (an accept, agree or acknowledge control). Links
// that lead to another page and controls that sign in, register, subscribe or open settings are never candidates.
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
    // a link that leads somewhere: only `<a href="#">` and `javascript:` links act as buttons
    const leads = (el) => el.tagName === 'A' && !/^(#|javascript:|$)/i.test((el.getAttribute('href') || '').trim());

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

    // the dialog over the target, or the modal one that made the target's part of the page inert
    const targetDialog = target.closest(DIALOGS);
    const blocks = (el) => el.matches(DIALOGS) && visible(el) && !el.contains(target);
    let dialog = null;
    for (let node = covering; node && dialog === null; node = node.parentElement) {
        if (blocks(node)) dialog = node;
    }
    if (dialog === null && covering) dialog = [...covering.querySelectorAll(DIALOGS)].find(blocks) || null;
    if (dialog === null && reason === 'inert') {
        const inert = target.closest('[inert]');
        dialog =
            [...document.querySelectorAll(DIALOGS)].find(
                (el) => blocks(el) && !inert.contains(el) && (el.matches(':modal') || el.getAttribute('aria-modal') === 'true')
            ) || null;
    }
    if (dialog === null) return null;

    // the dialog's own dismiss controls
    let close = null;
    let closeExact = null;
    let accept = null;
    for (const el of dialog.querySelectorAll(CONTROLS)) {
        if (!visible(el) || disabled(el) || leads(el)) continue;
        const name = normalized(accessibleName(el));
        // a control whose name starts with closing closes ("Dismiss sign-in info." closes, whatever else it names)
        if (CLOSE_GLYPHS.has(name) || CLOSE_START.test(name)) {
            if (closeExact === null) closeExact = el;
        } else if (ACCEPT.test(name)) {
            // before the looser close match: "Accept and close" accepts
            if (accept === null) accept = el;
        } else if (NEVER.test(name)) {
            // before the looser close match: "Sign in to close" signs in
            continue;
        } else if (CLOSE_WORD.test(name)) {
            if (close === null) close = el;
        } else if (name === '' && el.tagName !== 'A' && looksLikeClose(el)) {
            if (close === null) close = el;
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
