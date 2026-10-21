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
      `value_truncated` is then set) or the value of the selected option of a `<select>`. Password
      fields never expose their value or a digest: `filled` tells whether they hold one.
    - `value_digest`: a change marker of the full non-password value when `value` is truncated.
    - `checked`: checkbox / radio state (`.checked`, or `aria-checked` for ARIA widgets);
      `mixed` for `aria-checked="mixed"`.
    - `options`: the options of a `<select>` (the first 50, plus the selected ones; `options_truncated`
      is set when some are left out). They are data on the select's node, not actions of their own.
    - `expanded` / `selected` / `pressed`: `aria-expanded` / `aria-selected` / `aria-pressed`;
      `pressed` can also be `"mixed"` for toggle buttons with mixed formatting.
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
        replacement map) replaced in the value and the option values and labels."""
        literals = sorted((s for s in secrets if s), key=len, reverse=True)
        if not literals:
            return self

        def mask(text: str | None) -> str | None:
            if text is None:
                return None
            for literal in literals:
                text = text.replace(literal, secrets[literal])
            return text

        options = None
        if self.options is not None:
            options = tuple(
                option.model_copy(update={"value": mask(option.value), "label": mask(option.label)})
                for option in self.options
            )
        # a digest of a long value could reveal a secret it contains: drop it
        digest = None if self.value_digest is not None and mask(self.value) != self.value else self.value_digest
        return self.model_copy(update={"value": mask(self.value), "options": options, "value_digest": digest})

    def digest(self) -> str:
        """A stable string of the state, for fingerprints."""
        return self.model_dump_json(exclude_defaults=True)


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
