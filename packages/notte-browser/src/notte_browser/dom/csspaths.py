# functions from: https://github.com/browser-use/browser-use/blob/main/browser_use/browser/context.py
import re
from functools import lru_cache

from notte_core.logging import logger


def xpath_to_css_path(xpath: str) -> str:
    """Converts simple XPath expressions to CSS selectors."""
    if not xpath:
        return ""

    # Remove leading slash if present
    xpath = xpath.lstrip("/")

    # Split into parts
    parts: list[str] = xpath.split("/")
    css_parts = [_xpath_part_to_css(part) for part in parts if part]

    base_selector = " > ".join(css_parts)
    return base_selector


def child_css_path(parent_xpath: str, parent_css_path: str, xpath: str) -> str:
    """`xpath_to_css_path(xpath)`, extending `parent_css_path` (the CSS path of `parent_xpath`) when `xpath` is the
    parent's XPath plus one step, as an element's XPath is in the DOM payload. Converting each XPath from scratch
    would split the whole path again for every element."""
    prefix = parent_xpath + "/"
    part = xpath[len(prefix) :]
    if not xpath.startswith(prefix) or len(part) == 0 or "/" in part:
        return xpath_to_css_path(xpath)
    css_part = _xpath_part_to_css(part)
    # a parent XPath without steps has an empty CSS path, which is not joined
    return f"{parent_css_path} > {css_part}" if parent_xpath.strip("/") else css_part


# steps such as `div[3]` repeat across the elements of a page
@lru_cache(maxsize=4096)
def _xpath_part_to_css(part: str) -> str:
    # Handle index notation [n]
    if "[" not in part:
        return part
    base_part = part[: part.find("[")]
    index_part = part[part.find("[") :]

    # Handle multiple indices
    indices = [i.strip("[]") for i in index_part.split("]")[:-1]]

    for idx in indices:
        try:
            # Handle numeric indices
            if idx.isdigit():
                index = int(idx) - 1
                base_part += f":nth-of-type({index + 1})"
            # Handle last() function
            elif idx == "last()":
                base_part += ":last-of-type"
            # Handle position() functions
            elif "position()" in idx:
                if ">1" in idx:
                    base_part += ":nth-of-type(n+2)"
        except ValueError:
            continue

    return base_part


# Define a regex pattern for valid class names in CSS
_VALID_CLASS_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")

# Expanded set of safe attributes that are stable and useful for selection
_SAFE_ATTRIBUTES = frozenset(
    {
        # Data attributes (if they're stable in your application)
        "id",
        # Standard HTML attributes
        "name",
        "type",
        "placeholder",
        # Accessibility attributes
        "aria-label",
        "aria-labelledby",
        "aria-describedby",
        "role",
        # Common form attributes
        "for",
        "autocomplete",
        "required",
        "readonly",
        # Media attributes
        "alt",
        "title",
        "src",
        # Custom stable attributes (add any application-specific ones)
        "href",
        "target",
    }
)

_DYNAMIC_ATTRIBUTES = frozenset(
    {
        "data-id",
        "data-qa",
        "data-cy",
        "data-testid",
    }
)
_SAFE_AND_DYNAMIC_ATTRIBUTES = _SAFE_ATTRIBUTES | _DYNAMIC_ATTRIBUTES


def build_csspath(
    tag_name: str,
    xpath: str,
    attributes: dict[str, str],
    highlight_index: int | None,
    include_dynamic_attributes: bool = True,
    base_selector: str | None = None,
) -> str:
    """
    Creates a CSS selector for a DOM element, handling various edge cases and special characters.

    `base_selector` is `xpath_to_css_path(xpath)` when the caller already has it.
    """
    try:
        # Get base selector from XPath
        css_selector = xpath_to_css_path(xpath) if base_selector is None else base_selector

        # Handle class attributes
        if "class" in attributes and attributes["class"] and include_dynamic_attributes:
            # Iterate through the class attribute values
            classes = attributes["class"].split()
            for class_name in classes:
                # Skip empty class names
                if not class_name.strip():
                    continue

                # Check if the class name is valid
                if _VALID_CLASS_NAME.match(class_name):
                    # Append the valid class name to the CSS selector
                    css_selector += f".{class_name}"
                else:
                    # Skip invalid class names
                    continue

        safe_attributes = _SAFE_AND_DYNAMIC_ATTRIBUTES if include_dynamic_attributes else _SAFE_ATTRIBUTES

        # Handle other attributes
        for attribute, value in attributes.items():
            if attribute == "class":
                continue

            # Skip invalid attribute names
            if not attribute.strip():
                continue

            if attribute not in safe_attributes:
                continue

            # Escape special characters in attribute names
            safe_attribute = attribute.replace(":", r"\:")

            # Handle different value cases
            if value == "":
                css_selector += f"[{safe_attribute}]"
            elif any(char in value for char in "\"'<>`\n\r\t"):
                # Use contains for values with special characters
                # Regex-substitute *any* whitespace with a single space, then strip.
                collapsed_value = re.sub(r"\s+", " ", value).strip()
                # Escape embedded double-quotes.
                safe_value = collapsed_value.replace('"', '\\"')
                css_selector += f'[{safe_attribute}*="{safe_value}"]'
            else:
                css_selector += f'[{safe_attribute}="{value}"]'

        return css_selector

    except Exception:
        logger.opt(exception=True).debug("Failed to build CSS path; using the fallback selector")
        return f"{tag_name}[highlight_index='{highlight_index}']"
