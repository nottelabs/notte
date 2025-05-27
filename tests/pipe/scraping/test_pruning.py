import difflib
from pathlib import Path

from notte_browser.scraping.pruning import MarkdownPruningPipe, MaskedDocument
from pydantic import BaseModel


def test_mask_single_link() -> None:
    """Test masking a single link in markdown content."""
    content = "Here is a [link](https://example.com)"
    result = MarkdownPruningPipe.mask(content)

    assert result.content == "Here is a [link](link1)"
    assert result.links == {"link1": "https://example.com"}
    assert result.images == {}


def test_mask_single_image() -> None:
    """Test masking a single image in markdown content."""
    content = "Here is an ![image](https://example.com/img.jpg)"
    result = MarkdownPruningPipe.mask(content)

    assert result.content == "Here is an ![image](img1.png)"
    assert result.images == {"img1.png": "https://example.com/img.jpg"}
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

    assert "![image1](img1.png)" in result.content
    assert "![image2](img2.png)" in result.content
    assert "[link1](link1)" in result.content
    assert "[link2](link2)" in result.content
    assert result.images == {"img1.png": "https://example.com/img1.jpg", "img2.png": "https://example.com/img2.jpg"}
    assert result.links == {"link1": "https://example1.com", "link2": "https://example2.com"}


def test_unmask_single_link() -> None:
    """Test unmasking a single link reference."""
    doc = MaskedDocument(content="Here is a [text](link1)", links={"link1": "https://example.com"}, images={})
    result = MarkdownPruningPipe.unmask(doc)
    assert result == "Here is a [text](https://example.com)"


def test_unmask_single_image() -> None:
    """Test unmasking a single image reference."""
    doc = MaskedDocument(
        content="Here is an ![alt](img1.png)", links={}, images={"img1.png": "https://example.com/img.jpg"}
    )
    result = MarkdownPruningPipe.unmask(doc)
    assert result == "Here is an ![alt](https://example.com/img.jpg)"


def test_unmask_multiple_mixed() -> None:
    """Test unmasking multiple links and images."""
    doc = MaskedDocument(
        content=(
            "# Document\nHere is a [link1](link1) and ![image1](img1.png)\nAnother [link2](link2) and ![image2](img2.png)"
        ),
        links={"link1": "https://example1.com", "link2": "https://example2.com"},
        images={"img1.png": "https://example.com/img1.jpg", "img2.png": "https://example.com/img2.jpg"},
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

    assert "[link](link1)" in result.content
    assert "[another](link2)" in result.content  # Should preserve existing references
    assert "![image](img1.png)" in result.content


def test_unmask_with_missing_references() -> None:
    """Test unmasking with missing reference mappings."""
    doc = MaskedDocument(
        content="[text](link1) and ![image](img1.png) and [missing](link2)",
        links={"link1": "https://example.com"},
        images={"img1.png": "https://example.com/img.jpg"},
    )
    result = MarkdownPruningPipe.unmask(doc)

    assert "[text](https://example.com)" in result
    assert "![image](https://example.com/img.jpg)" in result
    assert "[missing](link2)" in result  # Should preserve unknown references


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
    assert result.content == "Here is an ![](img1.png)"
    assert result.images == {"img1.png": "image.png"}
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


class _TestModel(BaseModel):
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
        content="test", links={"link1": "https://example.com"}, images={"img1.png": "https://example.com/image.jpg"}
    )

    # Create a model with masked values
    model = _TestModel(title="Test", description="A test model", image_url="img1.png", link_url="link1", nested=None)

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
        content="test", links={"link1": "https://example.com"}, images={"img1.png": "https://example.com/image.jpg"}
    )

    # Create a model with masked values in nested dict
    model = _TestModel(
        title="Test",
        description="A test model",
        image_url="img1.png",
        link_url="link1",
        nested={
            "masked_image": "img1.png",
            "masked_link": "link1",
            "regular": "stays_same",
        },
    )

    # Unmask the model
    result = pipe.unmask_pydantic(masked_doc, model)

    assert result.nested is not None
    assert result.nested["masked_image"] == "https://example.com/image.jpg"
    assert result.nested["masked_link"] == "https://example.com"
    assert result.nested["regular"] == "stays_same"
    assert result.image_url == "https://example.com/image.jpg"
    assert result.link_url == "https://example.com"


class ListTestModel(BaseModel):
    items: list[_TestModel]


def test_unmask_pydantic_list() -> None:
    """Test unmasking a pydantic model with a list."""
    pipe = MarkdownPruningPipe()

    # Create a masked document
    masked_doc = MaskedDocument(
        content="test", links={"link1": "https://example.com"}, images={"img1.png": "https://example.com/image.jpg"}
    )

    # Create a model with masked values in nested dict
    model = ListTestModel(
        items=[
            _TestModel(title="Test", description="A test model", image_url="img1.png", link_url="link1", nested=None)
        ]
    )

    # Unmask the model
    result = pipe.unmask_pydantic(masked_doc, model)
    assert result.items[0].image_url == "https://example.com/image.jpg"
    assert result.items[0].link_url == "https://example.com"
    assert result.items[0].title == "Test"
    assert result.items[0].description == "A test model"


def test_mask_same_link_twice() -> None:
    """Test masking a link that appears twice in the content."""
    content = """
[Nike Air Max Dn8](https://www.nike.com/t/air-max-dn8-mens-shoes-YPsmAOxu/FQ7860-004)
[Nike Air Max Dn8 Men's Shoes](https://www.nike.com/t/air-max-dn8-mens-shoes-YPsmAOxu/FQ7860-004)
"""
    masked_content = """
[Nike Air Max Dn8](link1)
[Nike Air Max Dn8 Men's Shoes](link1)
"""
    result = MarkdownPruningPipe.mask(content)
    assert result.links == {"link1": "https://www.nike.com/t/air-max-dn8-mens-shoes-YPsmAOxu/FQ7860-004"}
    assert result.images == {}
    assert result.content == masked_content


def test_mask_link_with_image_reference() -> None:
    """Test masking a link that appears twice in the content."""
    content = """
[
    ![Image Alt](https://image.png) ![Empty Link]()
](https://link.com)
"""
    masked_content = """
[
    ![Image Alt](img1.png) ![Empty Link]()
](link1)
"""
    result = MarkdownPruningPipe.mask(content)
    assert result.images == {"img1.png": "https://image.png"}
    assert result.links == {"link1": "https://link.com"}
    assert result.content == masked_content


def test_complex_nested_links() -> None:
    """Test handling of complex nested image links with mixed content."""
    content = """
[Complex ![First](https://first.png) with text and ![Second](https://second.png)](https://link.com)
[Another ![Nested](https://deep.png)](https://another.com)
"""
    result = MarkdownPruningPipe.mask(content)

    assert result.images == {
        "img1.png": "https://first.png",
        "img2.png": "https://second.png",
        "img3.png": "https://deep.png",
    }
    assert result.links == {"link1": "https://link.com", "link2": "https://another.com"}

    # Verify the structure is preserved
    assert "Complex ![First](img1.png) with text and ![Second](img2.png)" in result.content
    assert "Another ![Nested](img3.png)" in result.content
    assert "(link1)" in result.content
    assert "(link2)" in result.content


def test_unmask_pydantic_json_content() -> None:
    """Test unmasking a pydantic model with JSON content."""
    pipe = MarkdownPruningPipe()

    # Create a model with markdown content that will be JSON serialized
    model = _TestModel(
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
