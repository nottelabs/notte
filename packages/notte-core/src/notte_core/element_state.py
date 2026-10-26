"""Live state of the interactive elements of a page, and a cheap fingerprint of a snapshot.

HTML attributes only give the initial state of a form control: `<input value="...">` is the value
the page was served with, not what was typed since; same for `checked` and the selected option of a
`<select>`. `buildDomNode.js` reads the live properties of every interactive element into a separate
`state` field of its payload, which `DomNode.state` carries. It is never rendered into the action
descriptions, so observing a page gives the same descriptions and action ids as before.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class SelectOption(BaseModel):
    """One `<option>` of a `<select>`: the value submitted and the label shown."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    value: str
    label: str
    selected: bool = False
    disabled: bool = False


class ElementState(BaseModel):
    """What an interactive element currently holds. Fields that do not apply to the element are `None`.

    - `value`: the current value of an input, textarea, contenteditable element (cut to 200 characters,
      `value_truncated` is then set), the value of the selected option of a `<select>`, or the
      `aria-valuetext` (else `aria-valuenow`) of an ARIA slider or spin button. Password
      fields never expose their value or a digest: `filled` tells whether they hold one.
    - `value_digest`: a change marker of the non-password value when `value` is truncated. Listbox
      button text reads stop after 1,024 nodes or 4,096 raw UTF-16 code units; beyond that cutoff,
      the digest covers only the text read and change detection is partial.
    - `checked`: checkbox / radio state (`.checked`, or `aria-checked` for ARIA widgets);
      `mixed` for `aria-checked="mixed"`.
    - `options`: the options of a `<select>` (the first 50, plus the selected ones; `options_truncated`
      is set when some are left out). They are data on the select's node, not actions of their own.
    - `expanded` / `selected` / `pressed`: `aria-expanded` / `aria-selected` / `aria-pressed`;
      `pressed` can also be `"mixed"` for toggle buttons with mixed formatting.
    - `sort`: the `aria-sort` of a column header, on the header and on the controls inside it (its sort
      button), when the column is sorted.
    - `draggable`: the element explicitly enables HTML drag and drop. This does not imply that
      clicking it drags it, or that its click action is unavailable.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True)

    value: str | None = None
    value_truncated: bool = Field(default=False, alias="valueTruncated")
    value_digest: str | None = Field(default=None, alias="valueDigest")
    filled: bool | None = None
    checked: bool | None = None
    mixed: bool | None = None
    options: tuple[SelectOption, ...] | None = None
    options_truncated: bool = Field(default=False, alias="optionsTruncated")
    multiple: bool | None = None
    expanded: bool | None = None
    selected: bool | None = None
    pressed: bool | Literal["mixed"] | None = None
    sort: Literal["ascending", "descending", "other"] | None = None
    draggable: bool | None = None

    @staticmethod
    def from_payload(payload: dict[str, Any] | None) -> "ElementState | None":
        """Reads the `state` field of a `buildDomNode.js` node (`None` when the node has none)."""
        if not payload:
            return None
        return ElementState.model_validate(payload)

    @property
    def selected_options(self) -> list[SelectOption]:
        return [option for option in self.options or () if option.selected]

    def masked(self, secrets: Mapping[str, str]) -> "ElementState":
        """A copy with every occurrence of a secret (`secrets` maps a value to its placeholder, e.g. a vault's
        replacement map) replaced in the field value: what the vault typed into the element.

        Select options are left as they are: they are the page's own content (already in the rendered
        description), and their values identify the option to select, so they must stay exact."""
        literals = sorted((s for s in secrets if s), key=len, reverse=True)
        if not literals:
            return self

        def mask(text: str | None) -> str | None:
            if text is None:
                return None
            for literal in literals:
                text = text.replace(literal, secrets[literal])
            return text

        value = mask(self.value)
        digest = self.value_digest
        if self.value_truncated:
            # The browser cut the value (and hashed the whole of it) before this runs: a secret can sit past the
            # cut, or across it. Mask a secret's start at the end of the cut value (this also covers a secret
            # longer than the cut), and drop the digest, which could confirm a guess of the hidden part.
            value = _mask_cut_secret(value, literals, secrets)
            digest = None
        elif value != self.value:
            digest = None
        return self.model_copy(update={"value": value, "value_digest": digest})

    def digest(self) -> str:
        """A stable string of the state, for fingerprints."""
        return self.model_dump_json(exclude_defaults=True)


# the shortest start of a secret masked at the end of a cut value (shorter ones match ordinary text too often)
MIN_CUT_SECRET_PREFIX = 3


def _mask_cut_secret(value: str | None, literals: list[str], secrets: Mapping[str, str]) -> str | None:
    if value is None:
        return None
    for literal in literals:
        for length in range(min(len(literal), len(value)), min(MIN_CUT_SECRET_PREFIX, len(literal)) - 1, -1):
            if value.endswith(literal[:length]):
                return value[: len(value) - length] + secrets[literal]
    return value


def page_fingerprint(url: str, elements: Iterable[tuple[str, str, ElementState | None]]) -> str:
    """A short hash of what a decision about a page depends on: its URL, and the id, label and live
    state of each interactive element (in order).

    Two snapshots with the same fingerprint offer the same actions on the same element values, so a
    decision taken on one still applies to the other. Geometry (scroll, bounding boxes) is left out
    on purpose: actions are resolved by selector when they run.
    """
    digest = hashlib.blake2b(digest_size=12)
    digest.update(url.encode())
    for element_id, label, state in elements:
        digest.update(b"\x00")
        digest.update(json.dumps([element_id, label, None if state is None else state.digest()]).encode())
    return digest.hexdigest()
