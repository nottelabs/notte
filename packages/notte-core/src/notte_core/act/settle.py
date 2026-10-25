"""The settle after an `act()` action: let the page react before it is observed again.

An action's effect often lands after the browser call returns. A combobox fetches its suggestions after
the input event; a client-side navigation fetches the next page, then `pushState`s and renders it.
Observed right away, the page is caught in between: the typed text without its suggestions (as if a value
were chosen), or the new URL with the old page's elements. The decider then acts on that page.

The session's `execute()` already waits for the page to settle after the actions that can start a navigation
(clicks, key presses, back / forward: `notte_browser.settle`), a new tab and a new document included. `act()`
settles the page the same way after its other actions (typing, selecting, checking, scrolling), which can
re-render the page or load more of it. After typing into an autocomplete field (a combobox, `aria-autocomplete`, a
listbox popup), it also waits for its visible suggestions to change, at most `EXPECT_MS` (the pause after typing
that let every city suggestion through in a Google Flights diagnostic; Google Flights renders them 90-160 ms
after the fill, with a request in flight from the first millisecond).

`SUGGESTIONS_JS` is evaluated right before the action. `NESTED_ROOTS` is the page script of the session's roots
(the page, its same-origin frames and open shadow roots: an autocomplete field can be in any of them); its
`changed()` returns whether the visible suggestions changed, `null` unless the focused element autocompletes.
"""

SUGGESTIONS_JS = """() => {
    const roots = NESTED_ROOTS;
    const deepActive = () => {
        let element = document.activeElement;
        for (;;) {
            if (element && element.shadowRoot && element.shadowRoot.activeElement) {
                element = element.shadowRoot.activeElement;
                continue;
            }
            let inner = null;
            if (element && (element.tagName === "IFRAME" || element.tagName === "FRAME")) {
                try { inner = element.contentDocument && element.contentDocument.activeElement; } catch (e) {}
            }
            if (!inner || inner === element) return element;
            element = inner;
        }
    };
    const autocompletes = (element) => {
        if (!element || element.tagName === "SELECT") return false;
        const autocomplete = element.getAttribute("aria-autocomplete");
        const popup = element.getAttribute("aria-haspopup");
        return element.getAttribute("role") === "combobox"
            || (autocomplete !== null && autocomplete !== "none")
            || popup === "listbox" || popup === "true";
    };
    const suggestions = () => roots.flatMap((root) => [...root.querySelectorAll("[role=option]")])
        .filter((option) => {
            const box = option.getBoundingClientRect();
            return box.width > 0 && box.height > 0;
        })
        .slice(0, 20)
        .map((option) => option.textContent.trim().slice(0, 80))
        .join("\\n");
    const before = suggestions();
    return { changed: () => autocompletes(deepActive()) ? suggestions() !== before : null };
}"""
