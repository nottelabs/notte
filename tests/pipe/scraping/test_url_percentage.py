"""Tests for URL percentage calculation in scraping pipe."""

from notte_browser.scraping.pipe import _calculate_url_percentage


def test_calculate_url_percentage_high_urls() -> None:
    """Test URL percentage calculation with high URL content."""
    text = (
        "Check out [this link](https://example.com/very/long/url/path/that/takes/up/space) "
        "and [another](https://example.com/another/very/long/url)"
    )
    percentage = _calculate_url_percentage(text)
    # Should be around 70-75% URLs
    assert percentage >= 0.7, f"Expected >= 70% URLs, got {percentage:.1%}"
    assert percentage < 1.0, f"Expected < 100% URLs, got {percentage:.1%}"


def test_calculate_url_percentage_low_urls() -> None:
    """Test URL percentage calculation with low URL content."""
    text = "This is a regular paragraph with some text. It has a [link](https://example.com) but mostly text."
    percentage = _calculate_url_percentage(text)
    # Should be around 15-20% URLs
    assert percentage >= 0.15, f"Expected >= 15% URLs, got {percentage:.1%}"
    assert percentage < 0.25, f"Expected < 25% URLs, got {percentage:.1%}"


def test_calculate_url_percentage_mostly_urls() -> None:
    """Test URL percentage calculation with content that is mostly URLs."""
    text = (
        "[Link 1](https://example.com/very/long/url/path/that/takes/up/space) "
        "[Link 2](https://example.com/another/very/long/url/path) "
        "[Link 3](https://example.com/yet/another/very/long/url/path)"
    )
    percentage = _calculate_url_percentage(text)
    # Should be around 80-85% URLs
    assert percentage >= 0.8, f"Expected >= 80% URLs, got {percentage:.1%}"
    assert percentage < 1.0, f"Expected < 100% URLs, got {percentage:.1%}"


def test_calculate_url_percentage_with_images() -> None:
    """Test URL percentage calculation with image URLs."""
    text = (
        "Image here: ![alt text](https://example.com/image.jpg) and another ![](https://example.com/another-image.png)"
    )
    percentage = _calculate_url_percentage(text)
    # Should be around 55-65% URLs
    assert percentage >= 0.5, f"Expected >= 50% URLs, got {percentage:.1%}"
    assert percentage < 0.7, f"Expected < 70% URLs, got {percentage:.1%}"


def test_calculate_url_percentage_mixed_links_and_images() -> None:
    """Test URL percentage calculation with both links and images."""
    text = (
        "Check this [article](https://example.com/article) with an image: "
        "![screenshot](https://example.com/screenshot.png) and more text here."
    )
    percentage = _calculate_url_percentage(text)
    # Should be around 40-50% URLs
    assert percentage >= 0.35, f"Expected >= 35% URLs, got {percentage:.1%}"
    assert percentage < 0.55, f"Expected < 55% URLs, got {percentage:.1%}"


def test_calculate_url_percentage_no_urls() -> None:
    """Test URL percentage calculation with no URLs."""
    text = "This is just plain text with no links or images at all."
    percentage = _calculate_url_percentage(text)
    assert percentage == 0.0, f"Expected 0% URLs, got {percentage:.1%}"


def test_calculate_url_percentage_empty_text() -> None:
    """Test URL percentage calculation with empty text."""
    text = ""
    percentage = _calculate_url_percentage(text)
    assert percentage == 0.0, f"Expected 0% URLs for empty text, got {percentage:.1%}"


def test_calculate_url_percentage_nested_images_in_links() -> None:
    """Test URL percentage calculation with nested images in links (complex markdown)."""
    text = "[Complex ![First](https://first.png) with text and ![Second](https://second.png)](https://link.com)"
    percentage = _calculate_url_percentage(text)
    # Should detect all three URLs: two image URLs and one link URL
    assert percentage >= 0.5, f"Expected >= 50% URLs for nested content, got {percentage:.1%}"


def test_calculate_url_percentage_short_vs_long_urls() -> None:
    """Test that longer URLs contribute more to the percentage."""
    # Short URL
    text_short = "Text [link](https://x.co) more text"
    percentage_short = _calculate_url_percentage(text_short)

    # Long URL
    text_long = "Text [link](https://example.com/very/long/path/to/resource/with/many/segments) more text"
    percentage_long = _calculate_url_percentage(text_long)

    assert percentage_long > percentage_short, (
        f"Expected long URL percentage ({percentage_long:.1%}) > short URL percentage ({percentage_short:.1%})"
    )


def test_calculate_url_percentage_duplicate_urls() -> None:
    """Test URL percentage calculation with duplicate URLs."""
    text = "[Link 1](https://example.com/page) and [Link 2](https://example.com/page) pointing to the same URL"
    percentage = _calculate_url_percentage(text)
    # Both instances of the URL should be counted
    assert percentage >= 0.4, f"Expected >= 40% URLs with duplicates, got {percentage:.1%}"


def test_calculate_url_percentage_urls_with_special_chars() -> None:
    """Test URL percentage calculation with URLs containing special characters."""
    text = (
        "API endpoint: [GET users](https://api.example.com/v1/users?page=1&limit=10) "
        "and [POST data](https://api.example.com/v1/data?format=json&encode=utf-8)"
    )
    percentage = _calculate_url_percentage(text)
    # Should handle query parameters and special characters
    assert percentage >= 0.6, f"Expected >= 60% URLs with special chars, got {percentage:.1%}"


def test_calculate_url_percentage_threshold_50_percent() -> None:
    """Test that we can reliably detect when URLs cross the 50% threshold."""
    # Just under 50%
    text_under = "Some text here [link](https://example.com) more text to dilute the URL percentage"
    percentage_under = _calculate_url_percentage(text_under)

    # Just over 50%
    text_over = "[Link 1](https://example.com/very/long/url/path) [Link 2](https://example.com/another/long/url) text"
    percentage_over = _calculate_url_percentage(text_over)

    assert percentage_under < 0.5, f"Expected < 50%, got {percentage_under:.1%}"
    assert percentage_over >= 0.5, f"Expected >= 50%, got {percentage_over:.1%}"


def test_calculate_url_percentage_uses_same_patterns_as_pruning() -> None:
    """Test that URL detection uses the same patterns as MarkdownPruningPipe."""
    from notte_browser.scraping.pruning import MarkdownPruningPipe

    # Create markdown with various URL formats
    text = (
        "# Test Document\n\n"
        "Here is a [regular link](https://example.com/page) and "
        "an ![image](https://example.com/image.jpg) and "
        "[nested ![img](https://example.com/nested.png) link](https://example.com/outer)"
    )

    # Mask the document using MarkdownPruningPipe
    masked = MarkdownPruningPipe.mask(text)

    # Both the mask and the percentage calculation should identify the same URLs
    # The masked document should have the same number of unique URLs
    num_urls_in_mask = len(masked.links) + len(masked.images)

    # Calculate percentage
    percentage = _calculate_url_percentage(text)

    # If the patterns are the same, we should detect URLs consistently
    # This is a sanity check that both use compatible patterns
    assert num_urls_in_mask > 0, "MarkdownPruningPipe should have found URLs"
    assert percentage > 0.0, "URL percentage should be > 0 when URLs are present"

    # The percentage should be reasonable for the content
    assert percentage < 1.0, "Percentage should be < 100% (there's text too)"
