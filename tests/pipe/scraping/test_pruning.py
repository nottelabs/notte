import difflib
from pathlib import Path

from notte_browser.scraping.pruning import MarkdownPruningPipe, MaskedDocument
from pydantic import BaseModel


def test_mask_single_link() -> None:
    """Test masking a single link in markdown content."""
    content = "Here is a [link](https://example.com)"
    result = MarkdownPruningPipe.mask(content)

    assert result.content == "Here is a [link](L1)"
    assert result.links == {"L1": "https://example.com"}
    assert result.images == {}


def test_mask_single_image() -> None:
    """Test masking a single image in markdown content."""
    content = "Here is an ![image](https://example.com/img.jpg)"
    result = MarkdownPruningPipe.mask(content)

    assert result.content == "Here is an ![image](F1)"
    assert result.images == {"F1": "https://example.com/img.jpg"}
    assert result.links == {}


def test_mask_multiple_mixed() -> None:
    """Test masking multiple links and images in the same content."""
    content = (
        "# Document\n"
        "Here is a [link1](https://example1.com) and "
        "![image1](https://example.com/img1.jpg)\n"
        "Another [link2](https://example2.com) and "
        "![image2](https://example.com/img2.jpg)"
    )
    result = MarkdownPruningPipe.mask(content)

    assert "![image1](F1)" in result.content
    assert "![image2](F2)" in result.content
    assert "[link1](L1)" in result.content
    assert "[link2](L2)" in result.content
    assert result.images == {"F1": "https://example.com/img1.jpg", "F2": "https://example.com/img2.jpg"}
    assert result.links == {"L1": "https://example1.com", "L2": "https://example2.com"}


def test_unmask_single_link() -> None:
    """Test unmasking a single link reference."""
    doc = MaskedDocument(content="Here is a [text](L1)", links={"L1": "https://example.com"}, images={})
    result = MarkdownPruningPipe.unmask(doc)
    assert result == "Here is a [text](https://example.com)"


def test_unmask_single_image() -> None:
    """Test unmasking a single image reference."""
    doc = MaskedDocument(content="Here is an ![alt](F1)", links={}, images={"F1": "https://example.com/img.jpg"})
    result = MarkdownPruningPipe.unmask(doc)
    assert result == "Here is an ![alt](https://example.com/img.jpg)"


def test_unmask_multiple_mixed() -> None:
    """Test unmasking multiple links and images."""
    doc = MaskedDocument(
        content=("# Document\nHere is a [link1](L1) and ![image1](F1)\nAnother [link2](L2) and ![image2](F2)"),
        links={"L1": "https://example1.com", "L2": "https://example2.com"},
        images={"F1": "https://example.com/img1.jpg", "F2": "https://example.com/img2.jpg"},
    )
    result = MarkdownPruningPipe.unmask(doc)

    assert "![image1](https://example.com/img1.jpg)" in result
    assert "![image2](https://example.com/img2.jpg)" in result
    assert "[link1](https://example1.com)" in result
    assert "[link2](https://example2.com)" in result


def test_mask_with_existing_reference_style() -> None:
    """Test masking content that already contains reference-style links."""
    content = (
        "Here is a [link](https://example.com) and a reference [another](ref) and ![image](https://example.com/img.jpg)"
    )
    result = MarkdownPruningPipe.mask(content)

    assert "[link](L1)" in result.content
    assert "[another](L2)" in result.content  # Should preserve existing references
    assert "![image](F1)" in result.content


def test_unmask_with_missing_references() -> None:
    """Test unmasking with missing reference mappings."""
    doc = MaskedDocument(
        content="[text](L1) and ![image](F1) and [missing](L2)",
        links={"L1": "https://example.com"},
        images={"F1": "https://example.com/img.jpg"},
    )
    result = MarkdownPruningPipe.unmask(doc)

    assert "[text](https://example.com)" in result
    assert "![image](https://example.com/img.jpg)" in result
    assert "[missing](L2)" in result  # Should preserve unknown references


def test_roundtrip() -> None:
    """Test that masking and then unmasking returns the original content."""
    original = (
        "# Document\n"
        "Here is a [link](https://example.com) and "
        "![image](https://example.com/img.jpg)\n"
        "Text with no links."
    )

    masked = MarkdownPruningPipe.mask(original)
    result = MarkdownPruningPipe.unmask(masked)

    assert result == original


def test_empty_image_placeholder_should_be_masked() -> None:
    """Test that empty image placeholders are masked."""
    content = "Here is an ![](image.png)"
    result = MarkdownPruningPipe.mask(content)
    assert result.content == "Here is an ![](F1)"
    assert result.images == {"F1": "image.png"}
    assert result.links == {}
    # unmask the result
    unmasked = MarkdownPruningPipe.unmask(result)
    assert unmasked == content


def format_diff_message(optim_text: str, incr_text: str) -> str:
    """Creates a detailed diff message between two texts."""
    diff: list[str] = list(difflib.ndiff(optim_text.splitlines(), incr_text.splitlines()))

    # Collect differences
    only_in_optim: list[str] = []
    only_in_incr: list[str] = []

    for line in diff:
        if line.startswith("- "):
            only_in_optim.append(line[2:])
        elif line.startswith("+ "):
            only_in_incr.append(line[2:])

    message: list[str] = []
    if only_in_optim:
        message.append("\nOnly in optimized prompt:")
        message.extend(f"  {line}" for line in only_in_optim)

    if only_in_incr:
        message.append("\nOnly in incremental prompt:")
        message.extend(f"  {line}" for line in only_in_incr)

    return "\n".join(message)


def test_roundtrip_real_data() -> None:
    """Test that masking and then unmasking returns the original content."""
    with open(Path(__file__).parent / "scraped_data.md", "r") as f:
        original = f.read()
    masked = MarkdownPruningPipe.mask(original)
    result = MarkdownPruningPipe.unmask(masked)
    # use difflib to compare the two strings
    assert result == original, format_diff_message(original, result)


class TestModel(BaseModel):
    title: str
    description: str
    image_url: str
    link_url: str
    nested: dict[str, str] | None = None


def test_unmask_pydantic_simple() -> None:
    """Test unmasking a simple pydantic model with direct replacements."""
    pipe = MarkdownPruningPipe()

    # Create a masked document
    masked_doc = MaskedDocument(
        content="test", links={"L1": "https://example.com"}, images={"F1": "https://example.com/image.jpg"}
    )

    # Create a model with masked values
    model = TestModel(title="Test", description="A test model", image_url="F1", link_url="L1", nested=None)

    # Unmask the model
    result = pipe.unmask_pydantic(masked_doc, model)

    assert result.image_url == "https://example.com/image.jpg"
    assert result.link_url == "https://example.com"
    assert result.title == "Test"
    assert result.description == "A test model"


def test_unmask_pydantic_nested() -> None:
    """Test unmasking a pydantic model with nested values."""
    pipe = MarkdownPruningPipe()

    # Create a masked document
    masked_doc = MaskedDocument(
        content="test", links={"L1": "https://example.com"}, images={"F1": "https://example.com/image.jpg"}
    )

    # Create a model with masked values in nested dict
    model = TestModel(
        title="Test",
        description="A test model",
        image_url="regular_url",
        link_url="regular_link",
        nested={"masked_image": "F1", "masked_link": "L1", "regular": "stays_same"},
    )

    # Unmask the model
    result = pipe.unmask_pydantic(masked_doc, model)

    assert result.nested is not None
    assert result.nested["masked_image"] == "https://example.com/image.jpg"
    assert result.nested["masked_link"] == "https://example.com"
    assert result.nested["regular"] == "stays_same"
    assert result.image_url == "regular_url"
    assert result.link_url == "regular_link"


def test_unmask_pydantic_json_content() -> None:
    """Test unmasking a pydantic model with JSON content."""
    pipe = MarkdownPruningPipe()

    # Create a model with markdown content that will be JSON serialized
    model = TestModel(
        title="Test with [link](https://example.com)",
        description="Image here: ![alt](https://example.com/image.jpg)",
        image_url="regular_url",
        link_url="regular_link",
        nested=None,
    )

    # First mask the content to get the masked document
    masked_title = MarkdownPruningPipe.mask(model.title)
    masked_desc = MarkdownPruningPipe.mask(model.description)

    masked_doc = MaskedDocument(
        content="test",
        links={**masked_title.links, **masked_desc.links},
        images={**masked_title.images, **masked_desc.images},
    )

    # Unmask the model
    result = pipe.unmask_pydantic(masked_doc, model)

    assert result.title == "Test with [link](https://example.com)"
    assert result.description == "Image here: ![alt](https://example.com/image.jpg)"
    assert result.image_url == "regular_url"
    assert result.link_url == "regular_link"
