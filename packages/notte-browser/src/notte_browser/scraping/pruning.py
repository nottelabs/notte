import functools
import re
from typing import Any, Callable, ClassVar, TypeVar

from loguru import logger
from pydantic import BaseModel

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


class MarkdownPruningPipe:
    """
    This pipe prunes the links and images from the markdown content.
    and replaces them with short placeholders.
    """

    # TODO: think about using markdown-it to handle nested images
    # First handle images - using non-greedy match for content between parentheses
    image_pattern: ClassVar[str] = r"!\[([^\]]*)\]\s*\(([^)]*?)\)"

    # Then handle links - using a pattern that can contain nested images
    link_pattern: ClassVar[str] = r"\[((?:[^\[\]]|\[(?:[^\[\]]|\[[^\[\]]*\])*\])*)\]\s*\(([^)]*?)\)"

    @staticmethod
    def image_mask(match: re.Match[str], images: dict[str, str]) -> str:
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

    @staticmethod
    def link_mask(match: re.Match[str], links: dict[str, str]) -> str:
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

    @staticmethod
    def mask(markdown_content: str) -> MaskedDocument:
        """
        Process markdown content to replace links and images with placeholders.
        Returns a Document with the processed content and mappings.
        """
        # Initialize storage for links and images
        links: dict[str, str] = {}
        images: dict[str, str] = {}

        def replace_images(content: str) -> str:
            """Replace image markdown with placeholders."""
            return re.sub(
                MarkdownPruningPipe.image_pattern, lambda match: MarkdownPruningPipe.image_mask(match, images), content
            )

        def replace_links(content: str) -> str:
            """Replace regular markdown links with placeholders."""
            return re.sub(
                MarkdownPruningPipe.link_pattern, lambda match: MarkdownPruningPipe.link_mask(match, links), content
            )

        # Apply transformations in sequence
        process = compose(replace_images, replace_links)
        processed_content = process(markdown_content)

        return MaskedDocument(content=processed_content, links=links, images=images)

    @staticmethod
    def unmask(masked_document: MaskedDocument) -> str:
        """
        Unmask the links and images from the document using regex pattern matching.
        Replaces inline-style placeholders with their original URLs.
        """

        def unmask_links(content: str) -> str:
            """Replace link placeholders with their original URLs."""
            pattern = MarkdownPruningPipe.link_pattern

            def replacement(match: re.Match[str]) -> str:
                text, placeholder = match.groups()
                return f"[{text}]({masked_document.links.get(placeholder, placeholder)})"

            return re.sub(pattern, replacement, content)

        def unmask_images(content: str) -> str:
            """Replace image placeholders with their original URLs."""
            pattern = MarkdownPruningPipe.image_pattern

            def replacement(match: re.Match[str]) -> str:
                alt_text, placeholder = match.groups()
                return f"![{alt_text}]({masked_document.images.get(placeholder, placeholder)})"

            return re.sub(pattern, replacement, content)

        # Apply transformations in sequence
        process = compose(unmask_images, unmask_links)
        return process(masked_document.content)

    @staticmethod
    def unmask_pydantic(document: MaskedDocument, data: TBaseModel) -> TBaseModel:
        """
        Unmask the links and images from the document using pydantic.
        """
        # Step 1: first try to unmask the JSON string
        json_document = document.with_content(data.model_dump_json())
        try:
            unmasked = MarkdownPruningPipe.unmask(json_document)
            data = data.__class__.model_validate_json(unmasked)
        except Exception as e:
            # if that fails, try to unmask the markdown string
            logger.debug(f"Failed to unmask the JSON string: {e}")

        # Step 2: look for string fields in the model that are exactly the same as the masked document
        def recursive_unmask(data: dict[str, Any]) -> dict[str, Any]:
            for key, value in data.items():
                if isinstance(value, str):
                    if value in document.links:
                        data[key] = document.links[value]
                    elif value in document.images:
                        data[key] = document.images[value]
                elif isinstance(value, dict):
                    data[key] = recursive_unmask(value)  # pyright: ignore[reportUnknownArgumentType]
                elif isinstance(value, list):
                    data[key] = [recursive_unmask(item) for item in value]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            return data

        unmasked_data = recursive_unmask(data.model_dump())
        return data.__class__.model_validate(unmasked_data)
