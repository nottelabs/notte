"""A cheap freshness check for `act()`: element signatures read by XPath with one script.

Right after observing, the session records the signature of every interaction element (tag, text,
value, checked / disabled / aria state, found at the element's XPath). Right before acting, it reads
the target's signature again: if it differs, or the URL changed, the decision is stale. The recorded
signature is read after the observation, so it is first checked against what the observation showed
(`Signatures.consistent`): a page that changed in between falls back to a new observation. This costs a
few milliseconds locally (one `page.evaluate`) and one `evaluate_js` call for cloud sessions, instead
of a full observation. Elements in iframes or shadow roots have no usable XPath: sessions fall back
to comparing a new observation (`same_target`).

On cloud sessions a script's result is recorded with the session's actions, so field values must not be
returned: `remote_signatures_expression` keeps the full baseline in the page and returns it without field
values or editable text (`store`), then compares in the page and returns only whether each element is
unchanged (`compare`).
"""

import json
from typing import Any, Literal, cast

from notte_core.act.space import ObservedPage, description_lines

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
            // what names the element from outside it: its <label>s and aria-labelledby targets
            [
                ...(el.labels ? Array.from(el.labels, label => label.innerText) : []),
                ...(el.getAttribute("aria-labelledby") || "").split(/\\s+/).filter(Boolean).map(ref => {
                    const root = el.getRootNode();
                    const target = (root.getElementById ? root : document).getElementById(ref);
                    return target ? target.textContent : null;
                }),
            ],
        ];
    }
    // the focused element (where Enter goes), by position in the document
    const active = document.activeElement;
    const focus = active && active !== document.body && active !== document.documentElement
        ? `${active.tagName}:${Array.prototype.indexOf.call(document.querySelectorAll("*"), active)}`
        : null;
    return { url: location.href, elements, focus };
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


# where the cloud baselines are kept in the page (a non-enumerable property of `window`), by token
_BASELINE_KEY = "__notteActSignatures"
# baselines kept per page: overlapping act() calls each have their own
_MAX_BASELINES = 16


def remote_signatures_expression(xpaths: dict[str, str], mode: Literal["store", "compare"], token: str) -> str:
    """An `evaluate_js` expression (a JSON string result) for cloud sessions, whose script results are recorded.

    - `store`: reads the signatures of `xpaths`, keeps them in the page under `token`, and returns them with no
      field value (only whether a password is filled) and no text of an editable element.
    - `compare`: reads them again and returns, by id, whether each is unchanged since the `store` of the same
      `token` (and the URL). Each act() call uses its own token, so overlapping calls never compare against
      each other's baseline.
    Field values never leave the page.
    """
    return f"""(() => {{
    const run = {ELEMENT_SIGNATURES_JS};
    const xpaths = {json.dumps(xpaths)};
    const current = run(xpaths);
    const key = {json.dumps(_BASELINE_KEY)};
    const token = {json.dumps(token)};
    if (!(window[key] instanceof Map)) {{
        Object.defineProperty(window, key, {{ value: new Map(), configurable: true, writable: true, enumerable: false }});
    }}
    const baselines = window[key];
    if ({json.dumps(mode)} === "store") {{
        baselines.delete(token);
        baselines.set(token, current);
        while (baselines.size > {_MAX_BASELINES}) baselines.delete(baselines.keys().next().value);
        const elements = {{}};
        for (const [id, signature] of Object.entries(current.elements)) {{
            if (signature === null) {{ elements[id] = null; continue; }}
            const copy = signature.slice();
            copy[2] = typeof copy[2] === "boolean" ? copy[2] : null;
            // an aria-labelledby target can be an editable element: keep its text in the page
            copy[15] = null;
            let el = null;
            try {{
                el = document.evaluate(xpaths[id], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            }} catch (e) {{}}
            if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) copy[1] = null;
            elements[id] = copy;
        }}
        return JSON.stringify({{ url: current.url, elements, focus: current.focus }});
    }}
    const stored = baselines.get(token);
    const unchanged = {{}};
    for (const id of Object.keys(xpaths)) {{
        unchanged[id] = Boolean(stored) && current.elements[id] !== null
            && JSON.stringify(stored.elements[id] ?? null) === JSON.stringify(current.elements[id]);
    }}
    const focusUnchanged = Boolean(stored) && stored.focus === current.focus;
    return JSON.stringify({{ url: current.url, unchanged, focusUnchanged }});
}})()"""


class Signatures:
    """The signatures recorded after an observation, and the comparison right before acting."""

    def __init__(self, result: dict[str, Any] | None) -> None:
        self.url: str | None = None if result is None else result.get("url")
        self.elements: dict[str, Any] = {} if result is None else dict(result.get("elements") or {})
        # the focused element, where a pressed key goes (None: the page body)
        self.focus: str | None = None if result is None else result.get("focus")

    def has(self, element_id: str) -> bool:
        return self.elements.get(element_id) is not None

    def unchanged(self, check: dict[str, Any] | None, element_id: str | None, *, focus: bool = False) -> bool:
        """A cloud `compare` result (`remote_signatures_expression`): same URL, `element_id` unchanged and, with
        `focus`, the same focused element."""
        if check is None or check.get("url") is None or check.get("url") != self.url:
            return False
        if focus and check.get("focusUnchanged") is not True:
            return False
        flags: Any = check.get("unchanged") or {}
        return element_id is None or (isinstance(flags, dict) and cast(dict[str, Any], flags).get(element_id) is True)

    def matches(self, current: "Signatures", element_id: str | None, *, focus: bool = False) -> bool:
        if current.url is None or current.url != self.url:
            return False
        if focus and current.focus != self.focus:
            return False
        return element_id is None or current.elements.get(element_id) == self.elements.get(element_id)

    def consistent(self, page: ObservedPage, element_id: str) -> bool:
        """The recorded signature of `element_id` describes the element of `page` (same tag, label text and,
        with live state, value, checked state and options). `False` when unsure: the caller then compares
        a new observation instead, which is slower but exact."""
        raw: Any = self.elements.get(element_id)
        action = next((a for a in page.actions if a.id == element_id), None)
        if action is None or not isinstance(raw, list):
            return False
        fields = cast(list[Any], raw)
        if len(fields) != _SIGNATURE_FIELDS:
            return False
        tag = str(fields[0]).lower()
        line = description_lines(page.description).get(element_id, "")
        if line.startswith("<") and not line.startswith(f"<{tag}"):
            return False
        label = _normalized(action.text_label or "").removesuffix("...")
        text = _normalized(str(fields[1] or ""))
        if label and text and label not in text and text not in label:
            return False
        state = page.states.get(element_id)
        if state is None:
            return True
        value, checked, options = fields[2], fields[3], fields[14]
        if state.filled is not None:
            return value == state.filled
        if state.value is not None and not state.value_truncated and isinstance(value, str) and value != state.value:
            return False
        if state.checked is not None and isinstance(checked, bool) and checked != state.checked:
            return False
        if state.options is not None and not state.options_truncated:
            listed = [(o.value, o.selected, o.disabled) for o in state.options]
            read = [tuple(o[:1] + o[2:]) for o in options] if isinstance(options, list) else None  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            return read == listed
        return True


# entries of an `ELEMENT_SIGNATURES_JS` signature: tag, text, value, checked, ..., options, external label texts
_SIGNATURE_FIELDS = 16


def _normalized(text: str) -> str:
    # innerText follows CSS text-transform and line breaks; labels come from the DOM text
    return " ".join(text.split()).lower()
