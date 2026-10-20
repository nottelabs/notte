"""Keep caller-provided variable literals out of later model requests in the same session."""

import html
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, cast
from urllib.parse import quote, quote_plus

from notte_core.act.space import ObservedPage


@dataclass
class ActPrivacy:
    # Retain old values too: callers may change a variable or omit variables on later calls.
    replacements: dict[str, str] = field(default_factory=dict, repr=False)

    def remember(self, variables: Mapping[str, str]) -> None:
        for name, value in variables.items():
            if not value:
                continue
            placeholder = "{{" + name + "}}"
            for literal in (value, html.escape(value), quote(value, safe=""), quote_plus(value)):
                self.replacements[literal] = placeholder
                # observe() caps field values at 200 UTF-16 code units. A protected
                # long value must not disclose its prefix through the capped state.
                prefix = literal.encode("utf-16-le")[:400].decode("utf-16-le", errors="surrogatepass")
                if len(prefix) < len(literal):
                    self.replacements[prefix] = placeholder

    def text(self, value: str) -> str:
        if not self.replacements:
            return value
        # One pass avoids replacing parts of placeholders emitted by another replacement.
        literals = "|".join(re.escape(key) for key in sorted(self.replacements, key=len, reverse=True))
        pattern = r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}|" + literals
        return re.sub(pattern, lambda match: self.replacements.get(match.group(), match.group()), value)

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
        return replace(
            page,
            url=self.text(page.url),
            title=self.text(page.title),
            description=description,
        )
