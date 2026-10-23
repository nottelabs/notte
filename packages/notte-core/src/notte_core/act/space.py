# The operation / target split of the questions, the strict answer validation and the element
# indexing are adapted from jev-ultrafast (`jev_ultrafast/model.py`: `action_space`, `choose`,
# `validate_choice`), Copyright (c) 2026 Browser Use, MIT License (see `LICENSE-jev-ultrafast`).
"""Turn an observed page into the questions of `act()`, and the answers back into a notte action.

Every interaction action of the observation becomes an element, indexed by its notte id (`B1`, `I3`).
One `operation` question picks what to do (CLICK, TYPE_TEXT, SELECT, a control, DONE or BLOCKED),
and one target question per operation picks the element: only the target question of the chosen
operation is used, the others are ignored. Native `<select>` options (from the live element state)
are SELECT targets `<id>:<n>`.

Two ways to show the page to the models (`NOTTE_ACT_LABELS`, see `label_mode`): `accessible` (default)
labels each element with its accessible name ("Search") and sends the visible text with `[I1] Search`
markers, closer to jev-ultrafast's page reading; a text or clickable `<label>` that names the field
next to it is not repeated as its own line or element. `html` labels each element with its rendered
HTML (`<input placeholder="Search">`) and sends the rendered page (`I1[:]<input ...>` lines).
"""

import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import notte_core.act.prompts as prompts
from notte_core.act.errors import InvalidDecisionError
from notte_core.act.types import Answer, Answers, PageState, Question
from notte_core.actions import (
    BaseAction,
    CheckAction,
    ClickAction,
    FillAction,
    GoBackAction,
    InteractionAction,
    PressKeyAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    WaitAction,
)
from notte_core.element_state import ElementState, SelectOption, page_fingerprint
from notte_core.observation import Observation
from notte_core.snapshot import ViewportData

MAX_ELEMENTS = 250
MAX_LABEL_LENGTH = 300
MAX_PAGE_TEXT_LENGTH = 12_000
WAIT_MS = 1_000

Operation = Literal["CLICK", "TYPE_TEXT", "SELECT"]
TargetKind = Literal["click", "check", "fill", "select_option", "select_text"]
LabelMode = Literal["html", "accessible"]

_DESCRIPTION_LINE = re.compile(r"^([A-Z]\d+)\[:\](.*)$")
# one rendered element (`I1[:]<input ...>`) or text (`_[:]Sign in`); its next lines continue it
_DESCRIPTION_BLOCK = re.compile(r"^([A-Z]\d+|_)\[:\](.*)$")
_RENDERED_ELEMENT = re.compile(r"^<(\w+)([^>]*)>(.*)</\1>$", re.DOTALL)
_RENDERED_ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')
# a text next to a field is taken as its label (the rendered page has no `<label for>` links) when short
MAX_NEARBY_LABEL_LENGTH = 80


def label_mode() -> LabelMode:
    """`NOTTE_ACT_LABELS`: `accessible` (default) or `html`, how elements and page text are shown to the models."""
    mode = os.getenv("NOTTE_ACT_LABELS", "accessible").strip().lower() or "accessible"
    if mode not in ("html", "accessible"):
        raise ValueError(f"NOTTE_ACT_LABELS must be 'html' or 'accessible', not {mode!r}")
    return "accessible" if mode == "accessible" else "html"


@dataclass(frozen=True)
class ObservedPage:
    """What `act()` needs from one observation of the page (local or remote session)."""

    url: str
    title: str
    description: str
    actions: Sequence[InteractionAction]
    viewport: ViewportData | None
    # live element state by action id (empty when a cloud observe response does not carry it)
    states: Mapping[str, ElementState]
    fingerprint: str
    # ids of the actions in the current viewport (from the screenshot's boxes; empty when unknown)
    in_view: frozenset[str] = frozenset()

    @staticmethod
    def from_observation(
        observation: Observation,
        states: Mapping[str, ElementState] | None = None,
        fingerprint: str | None = None,
    ) -> "ObservedPage":
        """Wrap an observation. The live state and fingerprint default to the observation's own (absent from
        an older server's observe response); without a fingerprint, it hashes the URL and the actions' ids
        and labels."""
        actions = list(observation.space.interaction_actions)
        url = observation.metadata.url
        if states is None:
            states = observation.element_states
        fingerprint = fingerprint or observation.fingerprint
        in_view = frozenset(
            box.notte_id
            for box in observation.screenshot.bboxes
            if box.notte_id is not None
            and box.absolute_y + box.height > 0
            and box.absolute_y < box.viewport_height
            and box.absolute_x + box.width > 0
            and box.absolute_x < box.viewport_width
        )
        return ObservedPage(
            url=url,
            title=observation.metadata.title,
            description=observation.space.description,
            actions=actions,
            viewport=observation.metadata.viewport,
            states=states or {},
            fingerprint=fingerprint or page_fingerprint(url, ((a.id, a.text_label or "", None) for a in actions)),
            in_view=in_view,
        )

    def signature(self, element_id: str) -> str | None:
        """What a decision about `element_id` depends on: its type, label and accessible name, selectors
        (including the iframe and shadow-root path used to execute it) and live state."""
        for action in self.actions:
            if action.id == element_id:
                selectors = action.selectors
                state = self.states.get(element_id)
                return "|".join(
                    [
                        action.type,
                        action.text_label or "",
                        action.accessible_name or "",
                        "" if selectors is None else selectors.model_dump_json(),
                        "" if state is None else state.digest(),
                    ]
                )
        return None


@dataclass(frozen=True)
class Target:
    key: str
    element_id: str
    kind: TargetKind
    label: str
    criteria: dict[str, Any]
    option: SelectOption | None = None
    checked: bool | None = None
    role: str = ""
    value: str | None = None


@dataclass(frozen=True)
class Control:
    key: str
    label: str
    action: BaseAction


@dataclass
class ActSpace:
    elements: list[dict[str, Any]] = field(default_factory=list)
    targets: dict[str, dict[str, Target]] = field(default_factory=dict)
    controls: dict[str, Control] = field(default_factory=dict)

    @property
    def operations(self) -> dict[str, str]:
        operations = {key: prompts.OPERATION_LABELS[key] for key in self.targets}
        operations.update({key: control.label for key, control in self.controls.items()})
        operations.update(DONE=prompts.DONE, BLOCKED=prompts.BLOCKED)
        return operations


def description_lines(description: str) -> dict[str, str]:
    """The rendered element of every action id in an action space description (`I1[:]<input ...>`), on one
    line: an element rendered over several lines (a `<select>` and its options) is joined with spaces."""
    lines: dict[str, str] = {}
    for key, content in _description_blocks(description):
        if key is not None and key != "_":
            _ = lines.setdefault(key, " ".join(content.splitlines()))
    return lines


def _description_blocks(description: str) -> list[tuple[str | None, str]]:
    """The rendered page as (`<id>` / `_` for text / None for a component header, content) blocks."""
    blocks: list[tuple[str | None, str]] = []
    for line in description.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _DESCRIPTION_BLOCK.match(line)
        if match is not None:
            blocks.append((match.group(1), match.group(2).strip()))
        elif line.startswith("### Content of "):
            blocks.append((None, line))
        elif len(blocks) > 0 and blocks[-1][0] is not None:
            # an element or text rendered over several lines
            blocks[-1] = (blocks[-1][0], blocks[-1][1] + "\n" + line)
        else:
            blocks.append(("_", line))
    return blocks


def _approximate_name(action: InteractionAction, rendered: str, before: str | None, after: str | None) -> str:
    """A name from the rendered element, for observations without `accessible_name` (an older server):
    `aria-label`, the label-like text or `<label>` next to a form field (before a text field, after a checkbox or
    radio), the button value or visible text, then `alt` / `placeholder` / `title`, notte's `text_label`, a link's
    `href`. Also the fallback of an element the observation leaves unnamed (without `before` / `after`)."""
    match = _RENDERED_ELEMENT.match(rendered)
    tag, attributes, content = "", dict[str, str](), ""
    if match is not None:
        tag = match.group(1).lower()
        attributes = dict(_RENDERED_ATTRIBUTE.findall(match.group(2)))
        content = " ".join(match.group(3).split())

    def nearby(text: str | None) -> str | None:
        return text if text is not None and len(text) <= MAX_NEARBY_LABEL_LENGTH else None

    role = _role(action, rendered)
    candidates = [attributes.get("aria_label")]
    if tag == "input" and attributes.get("type") in ("submit", "button", "reset"):
        candidates.append(attributes.get("value"))
    if role in ("checkbox", "radio"):
        candidates += [nearby(after), nearby(before)]
    elif role in ("textbox", "combobox", "select"):
        candidates.append(nearby(before))
    candidates += [content, attributes.get("alt"), attributes.get("placeholder"), attributes.get("title")]
    # an unnamed link (an icon) is at least its destination
    candidates += [action.text_label, attributes.get("href")]
    return next((c.strip() for c in candidates if c is not None and c.strip()), role)


@dataclass(frozen=True)
class _Names:
    # accessible name by action id
    names: dict[str, str]
    # description blocks that are the label of the element next to them (a text or a clickable `<label>`)
    used: frozenset[int]
    # clickable `<label>` elements that label the field next to them: the field is offered instead
    labels: frozenset[str]


def _same_text(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def _names(page: ObservedPage) -> _Names:
    """Each element's name: the observation's `accessible_name` (computed in the browser, like Chromium's), or
    for an observation without any (an older server) an approximation from the rendered page (`_approximate_name`).

    A text or clickable `<label>` next to a form field whose text is the field's name is the field's label: it is
    not repeated as a line of its own and, with real names, a clickable `<label>` is not offered as an element
    either (clicking it only focuses or toggles the field). Without real names the label stays an element, since
    its text may have been taken for the name of the wrong field."""
    blocks = _description_blocks(page.description)
    actions = {action.id: action for action in page.actions}
    real = any(action.accessible_name for action in page.actions)
    names: dict[str, str] = {}
    used: set[int] = set()
    labels: set[str] = set()

    def toggle(index: int) -> bool:
        action = actions.get(blocks[index][0] or "") if index >= 0 else None
        return action is not None and _role(action, blocks[index][1]) in ("checkbox", "radio")

    def label(index: int) -> str | None:
        """A text, or a `<label>` element (clickable labels get an id), that can name a field next to it."""
        if not 0 <= index < len(blocks) or blocks[index][0] is None:
            return None
        key, content = blocks[index]
        if key != "_":
            match = _RENDERED_ELEMENT.match(content)
            if match is None or match.group(1).lower() != "label":
                return None
            content = match.group(3)
        return " ".join(content.split()) or None

    for i, (key, content) in enumerate(blocks):
        action = actions.get(key or "")
        if key is None or action is None or key in names:
            continue
        role = _role(action, content)
        # the label right after a checkbox or radio is its own, not the next field's
        before = None if i >= 2 and toggle(i - 2) else label(i - 1)
        after = label(i + 1)
        if real:
            names[key] = (action.accessible_name or "").strip() or _approximate_name(action, content, None, None)
        else:
            names[key] = _approximate_name(action, content, before, after)
        if role in ("checkbox", "radio"):
            neighbours = [(i + 1, after), (i - 1, before)]
        elif role in _FIELDS:
            neighbours = [(i - 1, before)]
        else:
            neighbours = []
        for index, text in neighbours:
            if text is None or not _same_text(text, names[key]):
                continue
            label_key = blocks[index][0]
            if label_key == "_":
                used.add(index)
            elif real and label_key is not None:
                used.add(index)
                labels.add(label_key)
            break
    return _Names(
        names={k: v for k, v in names.items() if k not in labels}, used=frozenset(used), labels=frozenset(labels)
    )


# roles whose label is the text (or `<label>`) right before them
_FIELDS = ("textbox", "combobox", "select")


def accessible_names(page: ObservedPage) -> dict[str, str]:
    """The accessible name of every action rendered in the page description, by action id (clickable `<label>`
    elements that name the field next to them are left out: see `label_elements`)."""
    return _names(page).names


def label_elements(page: ObservedPage) -> frozenset[str]:
    """Ids of the clickable `<label>` elements that label the field next to them (only with real names)."""
    return _names(page).labels


def accessible_text(page: ObservedPage, display_text: Callable[[str], str] = str) -> str:
    """The page as visible text, each element replaced by `[<id>] <accessible name>` in reading order.

    The markers keep what the HTML rendering is needed for (where an element sits relative to the
    text: the price next to a button, the result a link opens) without its markup. The page's own
    component header is dropped; dialog headers are kept (they say a modal is open).
    """
    return "\n".join(line for _, line in _accessible_lines(page, display_text))


def _accessible_lines(page: ObservedPage, display_text: Callable[[str], str]) -> list[tuple[str | None, str]]:
    """`accessible_text` as (element id or None, line) pairs."""
    names = _names(page)
    lines: list[tuple[str | None, str]] = []
    for i, (key, content) in enumerate(_description_blocks(page.description)):
        if i in names.used:
            # already the name of the element next to it
            continue
        if key is None:
            if "'WebArea'" not in content:
                lines.append((None, content.removeprefix("### ")))
        elif key == "_":
            lines.append((None, content))
        else:
            marker = f"[{key}] {_cut(display_text(names.names.get(key, key)), MAX_LABEL_LENGTH)}"
            options = _rendered_options(page, key, content)
            if options:
                marker += f" (options: {_cut(display_text(', '.join(options)), MAX_LABEL_LENGTH)})"
            lines.append((key, marker))
    return lines


def _rendered_options(page: ObservedPage, key: str, rendered: str) -> list[str]:
    """The option labels of a `<select>` rendered over several lines, when the live state does not list them
    (a cloud observation without it): the decider and the writer still see what can be chosen."""
    state = page.states.get(key)
    if state is not None and state.options is not None:
        return []
    match = _RENDERED_ELEMENT.match(rendered)
    if match is None or match.group(1).lower() != "select":
        return []
    return [line.strip() for line in match.group(3).splitlines() if line.strip()]


def page_text(
    page: ObservedPage,
    labels: LabelMode = "html",
    display_text: Callable[[str], str] = str,
    length: int | None = None,
    focus: str | None = None,
    viewport_only: bool = False,
) -> str:
    """The page text sent to the models: the rendered description, or `accessible_text`.

    Only the elements in the viewport are offered, while the page text covers the whole page. On a page
    taller than the viewport (see `_viewport_lines`):
    - `viewport_only` (the text an action is decided on): the text of the viewport, and a line saying
      whether there is more above or below, as the elements offered are those the decider can see;
    - otherwise the whole text, with headers saying which part is above, in and below the viewport. Past
      `length`, it is cut around the viewport (around the `focus` element, when given), not at the top."""
    lines = _description_lines(page.description) if labels == "html" else _accessible_lines(page, display_text)
    viewport = _viewport_lines(page, lines)
    if viewport is None or viewport == (0, len(lines)):
        text = "\n".join(line for _, line in lines)
        return text if length is None else _cut(text, length)
    first, last = viewport
    shown = [line for _, line in lines]
    if viewport_only:
        text = "\n".join(shown[first:last])
        below = len("\n".join(shown[last:]))
        out = [NOT_SHOWN_ABOVE] if first > 0 else []
        out.append(text if length is None else _cut(text, length))
        if below > 0:
            out.append(NOT_SHOWN_BELOW.format(below))
        return "\n".join(out)
    start, end = 0, len(shown)
    if length is not None and len("\n".join(shown)) > length:
        shown = [_cut(line, length // 2) for line in shown]
        anchor = next((i for i, (key, _) in enumerate(lines) if key is not None and key == focus), first)
        start, end = _window(shown, anchor, length - _HEADERS_LENGTH)
    out = ["..."] if start > 0 else []
    region = None
    for i in range(start, end):
        current = ABOVE_VIEWPORT if i < first else IN_VIEWPORT if i < last else BELOW_VIEWPORT
        if current != region:
            out.append(current)
            region = current
        out.append(shown[i])
    if end < len(shown):
        out.append("...")
    return "\n".join(out)


ABOVE_VIEWPORT = "--- above the viewport ---"
IN_VIEWPORT = "--- in the viewport ---"
BELOW_VIEWPORT = "--- below the viewport: scroll down to reach ---"
NOT_SHOWN_ABOVE = "(page text above the viewport not shown: scroll up to read it)"
NOT_SHOWN_BELOW = "(about {} characters of page text below the viewport not shown: scroll down to read them)"
# the headers and "..." lines added to a cut page text
_HEADERS_LENGTH = len(ABOVE_VIEWPORT) + len(IN_VIEWPORT) + len(BELOW_VIEWPORT) + 16
# page text kept above the viewport when the text is cut around it
TEXT_ABOVE_VIEWPORT = 2_000
# two in-view elements further apart than this in the text are not in the same part of the page
# (a sticky header and the content scrolled to): a viewport holds a few thousand characters at most
_VIEWPORT_TEXT_GAP = 4_000


def _description_lines(description: str) -> list[tuple[str | None, str]]:
    """The rendered page's lines as (element id or None, line) pairs."""
    lines: list[tuple[str | None, str]] = []
    for line in description.splitlines():
        match = _DESCRIPTION_LINE.match(line.strip())
        lines.append((None if match is None else match.group(1), line))
    return lines


def _viewport_lines(page: ObservedPage, lines: Sequence[tuple[str | None, str]]) -> tuple[int, int] | None:
    """The lines `[first, last)` of the page text in the viewport, or None when the page fits in the viewport
    (or its size is unknown).

    The observation only says which elements are in view, not which text: the viewport is the run of in-view
    elements next to where the scroll position falls in the text (the scroll position as a fraction of the
    page height, applied to the text length), widened to that estimate when both agree. Without elements in
    view (a long article), it is the estimate alone."""
    viewport = page.viewport
    if viewport is None or viewport.total_height <= viewport.viewport_height + 2 or len(lines) == 0:
        return None
    starts: list[int] = []
    offset = 0
    for _, line in lines:
        starts.append(offset)
        offset += len(line) + 1
    length = offset
    low = viewport.scroll_y / viewport.total_height * length
    high = min(viewport.scroll_y + viewport.viewport_height, viewport.total_height) / viewport.total_height * length
    gap = max(_VIEWPORT_TEXT_GAP, high - low)
    ids = {key for key, _ in lines if key is not None}
    in_view = ids & page.in_view or ids
    clusters: list[list[int]] = []
    for i, (key, _) in enumerate(lines):
        if key not in in_view:
            continue
        if len(clusters) > 0 and starts[i] - starts[clusters[-1][-1]] <= gap:
            clusters[-1].append(i)
        else:
            clusters.append([i])

    def distance(cluster: list[int]) -> float:
        return max(0.0, starts[cluster[0]] - high, low - starts[cluster[-1]])

    # the lines the scroll position estimate covers
    estimate_first = next((i for i in range(len(lines)) if starts[i] + len(lines[i][1]) >= low), len(lines) - 1)
    estimate_last = max(estimate_first + 1, next((i for i in range(len(lines)) if starts[i] >= high), len(lines)))
    if len(clusters) == 0:
        return estimate_first, estimate_last
    cluster = min(clusters, key=lambda c: (distance(c), -len(c)))
    if distance(cluster) > gap:
        return cluster[0], cluster[-1] + 1
    return min(cluster[0], estimate_first), max(cluster[-1] + 1, estimate_last)


def _window(lines: Sequence[str], anchor: int, length: int) -> tuple[int, int]:
    """The lines `[start, end)` to send of a page text longer than `length`: from `TEXT_ABOVE_VIEWPORT` above the
    `anchor` line, as far down as `length` allows, then further up if the end of the page is reached."""
    start = anchor
    above = 0
    while start > 0 and above + len(lines[start - 1]) + 1 <= TEXT_ABOVE_VIEWPORT:
        start -= 1
        above += len(lines[start]) + 1
    end, used = start, 0
    while end < len(lines) and used + len(lines[end]) + 1 <= length:
        used += len(lines[end]) + 1
        end += 1
    while start > 0 and used + len(lines[start - 1]) + 1 <= length:
        start -= 1
        used += len(lines[start]) + 1
    return start, max(end, start + 1)


def _cut(text: str, length: int) -> str:
    return text if len(text) <= length else text[:length] + "..."


def _role(action: InteractionAction, line: str) -> str:
    # checkboxes and radios get a B (button) or I (input) id depending on their markup
    if line.startswith("<input") and ('type="checkbox"' in line or 'type="radio"' in line):
        return "radio" if 'type="radio"' in line else "checkbox"
    match action.id[:1], action.type:
        case "L", _:
            return "link"
        case "B", _:
            return "button"
        case "F", _:
            return "image"
        case "O", _:
            return "option"
        case "I", "fill":
            return "textbox"
        case "I", "check":
            return "radio" if 'type="radio"' in line else "checkbox"
        case "I", "select_dropdown_option":
            return "select" if line.startswith("<select") else "combobox"
        case _:
            return "clickable"


def _element(
    action: InteractionAction,
    label: str,
    role: str,
    state: ElementState | None,
    has_live_state: bool,
    display_text: Callable[[str], str],
    labels: LabelMode,
    display_cut: Callable[[str], str],
) -> dict[str, Any]:
    element: dict[str, Any] = {"index": action.id, "label": label, "role": role, "operations": []}
    # an accessible name already is the element's text
    if labels == "html" and action.text_label and action.text_label not in label:
        element["text"] = _cut(display_text(action.text_label), 120)
    if state is not None:
        if state.value is not None:
            element["value"] = (display_cut if state.value_truncated else display_text)(state.value)
        if state.filled is not None:
            element["filled"] = state.filled
        if state.checked is not None:
            element["checked"] = state.checked
        for key in ("expanded", "selected", "pressed"):
            value = getattr(state, key)
            if value is not None:
                element[key] = value
        if state.options is not None:
            element["value"] = display_text(", ".join(option.label for option in state.selected_options))
    elif has_live_state and role == "textbox":
        element["value"] = ""
    return element


def _offered(page: ObservedPage) -> list[InteractionAction]:
    """The actions offered to the decider, in page order: all of them, or past `MAX_ELEMENTS` the ones in the
    current viewport first, so that scrolling brings the others in reach."""
    actions = [action for action in page.actions if action.id]
    if len(actions) <= MAX_ELEMENTS:
        return actions
    kept = {action.id for action in actions if action.id in page.in_view}
    for action in actions:
        if len(kept) >= MAX_ELEMENTS:
            break
        kept.add(action.id)
    return [action for action in actions if action.id in kept][:MAX_ELEMENTS]


def build_act_space(
    page: ObservedPage,
    *,
    display_text: Callable[[str], str] = str,
    labels: LabelMode = "html",
    display_cut: Callable[[str], str] | None = None,
) -> ActSpace:
    """`display_text` masks the presentation strings; `display_cut` (default `display_text`) the live values the
    browser cut, where a protected value can start at the cut."""
    # Determine IDs, roles and supported operations from the original page. Only
    # presentation strings pass through display_text, before their display caps.
    lines = description_lines(page.description)
    names = _names(page) if labels == "accessible" else None
    space = ActSpace()
    has_live_state = len(page.states) > 0

    def add(operation: Operation, target: Target, element: dict[str, Any]) -> None:
        _ = space.targets.setdefault(operation, {}).__setitem__(target.key, target)
        if operation not in element["operations"]:
            element["operations"].append(operation)

    for action in _offered(page):
        if not action.id or (names is not None and action.id in names.labels):
            continue
        line = lines.get(action.id, "")
        shown = line if names is None else names.names.get(action.id)
        label = _cut(display_text(shown or action.text_label or action.id), MAX_LABEL_LENGTH)
        role = _role(action, line)
        state = page.states.get(action.id)
        element = _element(
            action, label, role, state, has_live_state, display_text, labels, display_cut or display_text
        )
        current = element.get("value")
        base: dict[str, Any] = {k: element[k] for k in ("role", "checked", "selected", "expanded") if k in element}

        def target(kind: TargetKind, key: str | None = None, option: SelectOption | None = None) -> Target:
            key = key or action.id
            shown = label if option is None else f"{label} → {display_text(option.label)}"
            criteria = {"element": f"[{key}] {shown}", "current_value": current or "", **base}
            if option is not None:
                criteria["option_value"] = display_text(option.value)
            return Target(
                key=key,
                element_id=action.id,
                kind=kind,
                label=shown,
                criteria=criteria,
                option=option,
                checked=None if state is None else state.checked,
                role=role,
                value=current,
            )

        match role:
            case "textbox":
                add("TYPE_TEXT", target("fill"), element)
                add("CLICK", target("click"), element)
            case "combobox":
                editable = (
                    (line.startswith(("<input", "<textarea")) and "readonly" not in line)
                    or 'contenteditable="true"' in line
                    or 'contenteditable="plaintext-only"' in line
                )
                add("TYPE_TEXT", target("fill" if editable else "select_text"), element)
                add("CLICK", target("click"), element)
            case "checkbox" | "radio":
                add("CLICK", target("check"), element)
            case "select":
                options = None if state is None else state.options
                if options is None:
                    # no live state (an observe response without it): the writer types the option label
                    add("TYPE_TEXT", target("select_text"), element)
                else:
                    listed: list[dict[str, str]] = []
                    element["options"] = listed
                    if state is not None and state.multiple:
                        # selecting an option replaces the current selection of a <select multiple>
                        element["multiple"] = True
                    for option in options:
                        if option.selected or option.disabled:
                            continue
                        key = f"{action.id}:{len(listed) + 1}"
                        listed.append(
                            {"index": key, "label": display_text(option.label), "value": display_text(option.value)}
                        )
                        add("SELECT", target("select_option", key, option), element)
                    if state is not None and state.options_truncated:
                        # long lists are cut (`ElementState.options`): the other options are typed by label
                        element["more_options"] = True
                        add("TYPE_TEXT", target("select_text"), element)
            case _:
                add("CLICK", target("click"), element)
        space.elements.append(element)

    viewport = page.viewport
    if viewport is None or viewport.scroll_y + viewport.viewport_height < viewport.total_height - 2:
        space.controls["SCROLL_DOWN"] = Control("SCROLL_DOWN", "Scroll down one page", ScrollDownAction())
    if viewport is None or viewport.scroll_y > 0:
        space.controls["SCROLL_UP"] = Control("SCROLL_UP", "Scroll up one page", ScrollUpAction())
    space.controls["PRESS_ENTER"] = Control(
        "PRESS_ENTER",
        "Press Enter in the focused field (e.g. submit a typed search that has no visible button)",
        PressKeyAction(key="Enter"),
    )
    space.controls["GO_BACK"] = Control("GO_BACK", "Go back to the previous page", GoBackAction())
    space.controls["WAIT"] = Control("WAIT", "Wait for the page to update", WaitAction(time_ms=WAIT_MS))
    return space


def page_state(
    page: ObservedPage,
    labels: LabelMode = "html",
    display_text: Callable[[str], str] = str,
    *,
    viewport_only: bool = False,
) -> PageState:
    text = page_text(page, labels, display_text, MAX_PAGE_TEXT_LENGTH, viewport_only=viewport_only)
    return PageState(url=page.url, title=page.title, text=text)


def act_questions(space: ActSpace, goal: str) -> dict[str, Question]:
    """The `operation` question and one target question per operation (jev-ultrafast's question set)."""
    questions = {
        "operation": Question(
            criteria=dict(space.operations), instructions={"goal": goal, "rules": prompts.NEXT_ACTION}
        )
    }
    for operation, candidates in space.targets.items():
        questions[_target_question(operation)] = Question(
            criteria={key: target.criteria for key, target in candidates.items()},
            instructions={"goal": goal, "operation": operation, "rules": [prompts.NEXT_ACTION, prompts.TARGET]},
        )
    return questions


def _target_question(operation: str) -> str:
    return operation.lower() + "_target"


def validate_answer(answers: Answers, question: str, keys: Mapping[str, Any]) -> Answer:
    """The answer to `question`, checked strictly: the choice is an offered option, there is a finite
    probability in [0, 1] for exactly the offered options, they sum to 1 and the choice is the most
    probable one. Raises `InvalidDecisionError` otherwise: nothing is executed on a malformed answer."""
    answer = answers.answers.get(question)
    if answer is None:
        raise InvalidDecisionError(f"no answer to question {question!r}")
    probabilities = answer.probabilities
    numbers = [*probabilities.values(), answer.confidence]
    valid = (
        answer.choice in keys
        and set(probabilities) == set(keys)
        and all(math.isfinite(n) and 0 <= n <= 1 for n in numbers)
        and abs(sum(probabilities.values()) - 1) < 0.02
        and probabilities[answer.choice] >= max(probabilities.values()) - 1e-6
    )
    if not valid:
        raise InvalidDecisionError(f"answer to {question!r} is not a valid choice among {len(keys)} options")
    return answer


@dataclass(frozen=True)
class Decision:
    operation: str
    operation_answer: Answer
    target: Target | None = None
    target_answer: Answer | None = None
    control: Control | None = None

    @property
    def confidence(self) -> float:
        if self.target_answer is None:
            return self.operation_answer.confidence
        return min(self.operation_answer.confidence, self.target_answer.confidence)

    @property
    def probabilities(self) -> dict[str, float]:
        if self.target_answer is not None:
            return dict(self.target_answer.probabilities)
        return dict(self.operation_answer.probabilities)


def interpret(answers: Answers, space: ActSpace) -> Decision:
    """Validate the operation answer, then only the target answer of the chosen operation."""
    operation_answer = validate_answer(answers, "operation", space.operations)
    operation = operation_answer.choice
    if operation in space.targets:
        candidates = space.targets[operation]
        target_answer = validate_answer(answers, _target_question(operation), candidates)
        return Decision(operation, operation_answer, candidates[target_answer.choice], target_answer)
    return Decision(operation, operation_answer, control=space.controls.get(operation))


def target_action(target: Target, text: str | None) -> InteractionAction:
    """The notte action for a chosen target. `text` is the (variable-substituted) value to type."""
    match target.kind:
        case "click":
            return ClickAction(id=target.element_id)
        case "check":
            if target.checked is None:
                return ClickAction(id=target.element_id)
            return CheckAction(id=target.element_id, value=not target.checked)
        case "fill":
            assert text is not None
            return FillAction(id=target.element_id, value=text)
        case "select_option":
            assert target.option is not None
            return SelectDropdownOptionAction(id=target.element_id, value=target.option.value)
        case "select_text":
            assert text is not None
            return SelectDropdownOptionAction(id=target.element_id, value=text)


def needs_text(target: Target) -> bool:
    return target.kind in ("fill", "select_text")


_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def substitute_variables(text: str, variables: Mapping[str, str]) -> str:
    """Replace every `{{name}}` of a known variable by its value (unknown names are left as they are)."""
    return _VARIABLE.sub(lambda match: variables.get(match.group(1), match.group(0)), text)
