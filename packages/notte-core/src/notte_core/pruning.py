import functools
import re
from typing import Any, Callable, TypeVar, cast

from pydantic import BaseModel

from notte_core.logging import logger

T = TypeVar("T")
TBaseModel = TypeVar("TBaseModel", bound=BaseModel)


class MaskedDocument(BaseModel):
    content: str
    links: dict[str, str]
    images: dict[str, str]

    def with_content(self, content: str) -> "MaskedDocument":
        return MaskedDocument(content=content, links=self.links, images=self.images)


def compose(*functions: Callable[[T], T]) -> Callable[[T], T]:
    """Compose multiple functions from left to right."""
    return functools.reduce(lambda f, g: lambda x: g(f(x)), functions)


# TODO: think about using markdown-it to handle nested images
# First handle images - using non-greedy match for content between parentheses
IMAGE_PATTERN: str = r"!\[([^\]]*)\]\s*\(([^)]*?)\)"

# Then handle links - using a pattern that can contain nested images
LINK_PATTERN: str = r"\[((?:[^\[\]]|\[(?:[^\[\]]|\[[^\[\]]*\])*\])*)\]\s*\(([^)]*?)\)"


def _mask_image(match: re.Match[str], images: dict[str, str]) -> str:
    alt_text, url = match.groups()
    # Skip empty URLs
    if not url.strip():
        return f"![{alt_text}]()"

    if url in images.values():
        # already masked => reuse the same placeholder
        placeholder = next(k for k, v in images.items() if v == url)
    else:
        placeholder = f"img{len(images) + 1}.png"
        images[placeholder] = url
    return f"![{alt_text}]({placeholder})"


def _mask_link(match: re.Match[str], links: dict[str, str]) -> str:
    text, url = match.groups()
    # Skip if the URL is already a placeholder reference
    if url.startswith("img"):
        return match.group(0)

    if url in links.values():
        # already masked => reuse the same placeholder
        placeholder = next(k for k, v in links.items() if v == url)
    else:
        placeholder = f"link{len(links) + 1}"
        links[placeholder] = url
    return f"[{text}]({placeholder})"


def mask_markdown(markdown_content: str) -> MaskedDocument:
    """
    Process markdown content to replace links and images with placeholders.
    Returns a Document with the processed content and mappings.
    """
    # Initialize storage for links and images
    links: dict[str, str] = {}
    images: dict[str, str] = {}

    def replace_images(content: str) -> str:
        """Replace image markdown with placeholders."""
        return re.sub(IMAGE_PATTERN, lambda match: _mask_image(match, images), content)

    def replace_links(content: str) -> str:
        """Replace regular markdown links with placeholders."""
        return re.sub(LINK_PATTERN, lambda match: _mask_link(match, links), content)

    # Apply transformations in sequence
    process = compose(replace_images, replace_links)
    processed_content = process(markdown_content)

    return MaskedDocument(content=processed_content, links=links, images=images)


def unmask_markdown(masked_document: MaskedDocument) -> str:
    """
    Unmask the links and images from the document using regex pattern matching.
    Replaces inline-style placeholders with their original URLs.
    """

    def unmask_links(content: str) -> str:
        """Replace link placeholders with their original URLs."""
        pattern = LINK_PATTERN

        def replacement(match: re.Match[str]) -> str:
            text, placeholder = match.groups()
            return f"[{text}]({masked_document.links.get(placeholder, placeholder)})"

        return re.sub(pattern, replacement, content)

    def unmask_images(content: str) -> str:
        """Replace image placeholders with their original URLs."""
        pattern = IMAGE_PATTERN

        def replacement(match: re.Match[str]) -> str:
            alt_text, placeholder = match.groups()
            return f"![{alt_text}]({masked_document.images.get(placeholder, placeholder)})"

        return re.sub(pattern, replacement, content)

    # Apply transformations in sequence
    process = compose(unmask_images, unmask_links)
    return process(masked_document.content)


def unmask_pydantic(document: MaskedDocument, data: TBaseModel) -> TBaseModel:
    """
    Unmask the links and images from the document using pydantic.
    """
    # Step 1: first try to unmask the JSON string
    json_document = document.with_content(data.model_dump_json())
    try:
        unmasked = unmask_markdown(json_document)
        data = data.__class__.model_validate_json(unmasked)
    except Exception as e:
        # if that fails, try to unmask the markdown string
        logger.debug(f"Failed to unmask the JSON string: {e}")

    # Step 2: look for string fields in the model that are exactly the same as the masked document
    def recursive_unmask(value: Any) -> Any:
        if isinstance(value, str):
            if value in document.links:
                return document.links[value]
            if value in document.images:
                return document.images[value]
            return value
        if isinstance(value, dict):
            return {key: recursive_unmask(item) for key, item in cast(dict[str, Any], value).items()}
        if isinstance(value, list):
            return [recursive_unmask(item) for item in cast(list[Any], value)]
        return value

    unmasked_data = recursive_unmask(data.model_dump())
    return data.__class__.model_validate(unmasked_data)
