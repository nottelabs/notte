import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from notte_core.utils.raw_file import get_file_ext, get_filename


@pytest.mark.parametrize(
    "url,expected_extension",
    [
        # Basic cases
        ("https://example.com/file.pdf", "pdf"),
        ("https://example.com/image.png", "png"),
        ("https://example.com/document.docx", "docx"),
        # URLs with query parameters
        ("https://example.com/file.pdf?version=1&format=print", "pdf"),
        ("https://example.com/image.png?width=800&height=600", "png"),
        ("https://example.com/document.docx?download=true", "docx"),
        # URLs with fragments
        ("https://example.com/file.pdf#page=5", "pdf"),
        ("https://example.com/image.png#section1", "png"),
        # URLs with both query and fragment
        ("https://example.com/file.pdf?version=1#page=5", "pdf"),
        ("https://example.com/image.png?width=800#section1", "png"),
        # URLs without extension
        ("https://example.com/file", None),
        ("https://example.com/file?query=value", None),
        ("https://example.com/file#fragment", None),
        # URLs with unsupported extensions
        ("https://example.com/file.txt", None),
        ("https://example.com/file.html", None),
        # Edge cases
        (None, None),
        ("", None),
        ("https://example.com/file.", None),
        ("https://example.com/.pdf", "pdf"),
    ],
)
def test_get_file_ext(url: str | None, expected_extension: str | None) -> None:
    """Test get_file_ext function with various URL formats."""
    result = get_file_ext(None, url)
    assert result == expected_extension, f"Expected {expected_extension}, got {result} for URL {url}"


@pytest.mark.parametrize(
    "headers,url,expected_filename_pattern",
    [
        # Test with content-disposition header
        (
            {"content-disposition": 'attachment; filename="document.pdf"'},
            "https://example.com/download",
            r"^2023_02_13_23_31_30-document\.pdf$",
        ),
        # Test with content-disposition and forward slash
        (
            {"content-disposition": 'attachment; filename="folder/file.txt"'},
            "https://example.com/download",
            r"^2023_02_13_23_31_30-folder-file\.txt$",
        ),
        # Test with filename*= encoding - should fall back to URL
        (
            {"content-disposition": "attachment; filename*=UTF-8''na%C3%AFve%20file.txt"},
            "https://downloads.example.com/file",
            r"^2023_02_13_23_31_30-downloads\.example\.com$",
        ),
        # Test with both filename and filename*= - should use filename
        (
            {"content-disposition": 'attachment; filename="simple.txt"; filename*=UTF-8encoded%20file.txt'},
            "https://example.com/download",
            r"^2023_02_13_23_31_30-simple\.txt$",
        ),
        # Test with only filename*= (no regular filename) - should fall back to URL
        (
            {"content-disposition": "attachment; filename*=ISO-8859-1'en'%A3%20rates"},
            "https://files.example.org/data",
            r"^2023_02_13_23_31_30-files\.example\.org$",
        ),
        # Test filename*= with content-type - should fall back to URL + extension
        (
            {"content-disposition": "attachment; filename*=UTF-8''document%2Epdf", "content-type": "application/pdf"},
            "https://docs.example.com/report",
            r"^2023_02_13_23_31_30-docs\.example\.com\.pdf$",
        ),
        # Test without content-disposition, with hostname and content-type
        (
            {"content-type": "image/jpeg"},
            "https://images.example.com/photo",
            r"^2023_02_13_23_31_30-images\.example\.com\.jpg$",
        ),
        # Test with content-disposition containing special characters
        (
            {"content-disposition": 'inline; filename="report (final).xlsx"'},
            "https://example.com/reports",
            r"^2023_02_13_23_31_30-report \(final\)\.xlsx$",
        ),
        # Test with PNG content type
        (
            {"content-type": "image/png"},
            "https://cdn.example.com/assets",
            r"^2023_02_13_23_31_30-cdn\.example\.com\.png$",
        ),
    ],
)
@patch("notte_core.utils.raw_file.dt.datetime")
def test_get_filename_patterns(
    mock_datetime: MagicMock, headers: dict[str, Any], url: str, expected_filename_pattern: str
) -> None:
    # Mock dt.datetime.now() to return a consistent timestamp
    mock_now = mock_datetime.now.return_value
    mock_now.strftime.return_value = "2023_02_13_23_31_30"

    result = get_filename(headers, url)

    # Check that the result matches the expected pattern
    assert re.match(expected_filename_pattern, result), f"Expected pattern {expected_filename_pattern}, got {result}"

    # Verify timestamp is included
    assert result.startswith("2023_02_13_23_31_30-")
