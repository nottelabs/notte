"""Keep caller-provided variable literals and vault secrets out of later model requests in the same session."""

import html
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, cast
from urllib.parse import quote, quote_plus

from notte_core.act.space import ObservedPage

# whitespace inside a protected value as the page may show it: spaces, line breaks, or a break onto the next line of
# the rendered page, after that line's element prefix (`_[:]`, `I1[:]`)
_LINE_BREAK = r"(?:\n[ \t]*(?:[A-Z]\d+|_)\[:\]|\s)+"


@dataclass
class ActPrivacy:
    # Retain old values too: callers may change a variable or omit variables on later calls.
    replacements: dict[str, str] = field(default_factory=dict, repr=False)

    def remember(self, variables: Mapping[str, str]) -> None:
        for name, value in variables.items():
            self._protect(value, "{{" + name + "}}")

    def remember_secrets(self, replacements: Mapping[str, str]) -> None:
        """Credential values the vault already typed (read back by the live state), by vault placeholder."""
        for value, placeholder in replacements.items():
            self._protect(value, placeholder)

    def _protect(self, value: str, placeholder: str) -> None:
        if not value:
            return
        for literal in (value, html.escape(value), quote(value, safe=""), quote_plus(value)):
            self.replacements[literal] = placeholder
            # observe() caps field values at 200 UTF-16 code units. A protected
            # long value must not disclose its prefix through the capped state.
            prefix = literal.encode("utf-16-le")[:400].decode("utf-16-le", errors="surrogatepass")
            if len(prefix) < len(literal):
                self.replacements[prefix] = placeholder

    def cut_text(self, value: str) -> str:
        """`text` for a live field value the browser cut (`ElementState.value_truncated`): a protected value
        can also start at the cut, with only its first characters visible. Those are masked too (from 3
        characters: shorter starts match ordinary text too often)."""
        value = self.text(value)
        for literal in sorted(self.replacements, key=len, reverse=True):
            for length in range(min(len(literal), len(value)), min(3, len(literal)) - 1, -1):
                if value.endswith(literal[:length]):
                    return value[: len(value) - length] + self.replacements[literal]
        return value

    def text(self, value: str) -> str:
        if not self.replacements:
            return value
        # One pass avoids replacing parts of placeholders emitted by another replacement.
        literals = "|".join(re.escape(key) for key in sorted(self.replacements, key=len, reverse=True))
        pattern = r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}|" + literals
        value = re.sub(pattern, lambda match: self.replacements.get(match.group(), match.group()), value)
        return self._multiline(value)

    def _multiline(self, value: str) -> str:
        """Mask the protected values that span lines wherever the page shows them: with other whitespace between
        their lines, or as consecutive lines of the rendered page (each with its `_[:]` / `I1[:]` prefix)."""
        for literal in sorted(self.replacements, key=len, reverse=True):
            if "\n" not in literal and "\r" not in literal:
                continue
            parts = [re.escape(part) for part in re.split(r"\s+", literal.strip()) if part]
            if len(parts) < 2:
                continue
            value = re.sub(_LINE_BREAK.join(parts), self.replacements[literal], value)
        return value

    def payload(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.payload(item) for item in cast(list[Any], value)]
        if isinstance(value, dict):
            return {key: self.payload(item) for key, item in cast(dict[str, Any], value).items()}
        return value

    def page(self, page: ObservedPage) -> ObservedPage:
        # This copy supplies only display metadata/text, never action structure.
        # Preserve rendered action-ID prefixes that the model uses as references.
        description = "\n".join(
            match[1] + self.text(match[2])
            if (match := re.match(r"^(\s*[A-Z]\d+\[:\])(.*)$", line))
            else self.text(line)
            for line in page.description.split("\n")
        )
        # a value with a line break is rendered as two lines: mask it across them too
        description = self._multiline(description)
        return replace(
            page,
            url=self.text(page.url),
            title=self.text(page.title),
            description=description,
        )
