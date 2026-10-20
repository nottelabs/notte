"""A cheap freshness check for `act()`: element signatures read by XPath with one script.

Right after observing, the session records the signature of every interaction element (tag, text,
value, checked / disabled / aria state, found at the element's XPath). Right before acting, it reads
the target's signature again: if it differs, or the URL changed, the decision is stale. This costs a
few milliseconds locally (one `page.evaluate`) and one `evaluate_js` call for cloud sessions, instead
of a full observation. Elements in iframes or shadow roots have no usable XPath: sessions fall back
to comparing a new observation (`same_target`).
"""

import json
from typing import Any

from notte_core.act.space import ObservedPage

ELEMENT_SIGNATURES_JS = """(xpaths) => {
    const elements = {};
    for (const [id, xpath] of Object.entries(xpaths)) {
        let el = null;
        try {
            el = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        } catch (e) {}
        if (!el || !el.isConnected) { elements[id] = null; continue; }
        elements[id] = [
            el.tagName,
            el.innerText ?? el.textContent ?? "",
            el.type === "password" ? Boolean(el.value) : ("value" in el ? String(el.value) : null),
            el.checked ?? null,
            el.disabled ?? null,
            el.getAttribute("aria-expanded"),
            el.getAttribute("aria-selected"),
            el.getAttribute("aria-checked"),
            el.getAttribute("aria-pressed"),
            el.getAttribute("aria-label"),
            el.getAttribute("role"),
            el.getAttribute("type"),
            el.readOnly ?? null,
            el.href ?? null,
            el.options ? Array.from(el.options, option => [
                option.value, option.label, option.selected,
                option.disabled || Boolean(option.closest("optgroup[disabled]"))
            ]) : null,
        ];
    }
    return { url: location.href, elements };
}"""


def signature_xpaths(page: ObservedPage, element_id: str | None = None) -> dict[str, str]:
    """The XPath of every interaction element (or only `element_id`) outside iframes and shadow roots."""
    xpaths: dict[str, str] = {}
    for action in page.actions:
        if element_id is not None and action.id != element_id:
            continue
        selectors = action.selectors
        if selectors is None or selectors.in_iframe or selectors.in_shadow_root or not selectors.xpath_selector:
            continue
        xpaths[action.id] = selectors.xpath_selector
    return xpaths


def signatures_expression(xpaths: dict[str, str]) -> str:
    """`ELEMENT_SIGNATURES_JS` applied to `xpaths`, as one expression returning a JSON string (for `evaluate_js`).

    An immediately invoked function: the cloud API returns `null` for some other shapes of expression
    (e.g. `JSON.stringify((fn)(args))` when `fn` has a block body).
    """
    return f"(() => {{ const run = {ELEMENT_SIGNATURES_JS}; return JSON.stringify(run({json.dumps(xpaths)})); }})()"


class Signatures:
    """The signatures recorded after an observation, and the comparison right before acting."""

    def __init__(self, result: dict[str, Any] | None) -> None:
        self.url: str | None = None if result is None else result.get("url")
        self.elements: dict[str, Any] = {} if result is None else dict(result.get("elements") or {})

    def has(self, element_id: str) -> bool:
        return self.elements.get(element_id) is not None

    def matches(self, current: "Signatures", element_id: str | None) -> bool:
        if current.url is None or current.url != self.url:
            return False
        return element_id is None or current.elements.get(element_id) == self.elements.get(element_id)
