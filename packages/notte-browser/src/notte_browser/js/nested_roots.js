// The page's document, then its same-origin frames' documents and open shadow roots (nested ones too), at most 50:
// the scripts that watch the page observe all of them.
(() => {
    const roots = [document];
    for (let i = 0; i < roots.length && roots.length < 50; i++) {
        for (const el of roots[i].querySelectorAll("*")) {
            if (roots.length >= 50) break;
            if (el.shadowRoot) roots.push(el.shadowRoot);
            if (el.tagName === "IFRAME" || el.tagName === "FRAME") {
                try { if (el.contentDocument) roots.push(el.contentDocument); } catch (e) {}
            }
        }
    }
    return roots;
})()
