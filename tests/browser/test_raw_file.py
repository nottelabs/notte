import re
from unittest.mock import patch

import pytest
from notte_core.utils.raw_file import get_filename


@pytest.mark.parametrize(
    "headers,url,expected_filename_pattern",
    [
        # Test with content-disposition header
        (
            {"content-disposition": 'attachment; filename="document.pdf"'},
            "https://example.com/download",
            r"^\d+-document\.pdf$",
        ),
        # Test with content-disposition and forward slash
        (
            {"content-disposition": 'attachment; filename="folder/file.txt"'},
            "https://example.com/download",
            r"^\d+-folder-file\.txt$",
        ),
        # Test with filename*= encoding - should fall back to URL
        (
            {"content-disposition": "attachment; filename*=UTF-8''na%C3%AFve%20file.txt"},
            "https://downloads.example.com/file",
            r"^\d+-downloads\.example\.com$",
        ),
        # Test with both filename and filename*= - should use filename
        (
            {"content-disposition": 'attachment; filename="simple.txt"; filename*=UTF-8encoded%20file.txt'},
            "https://example.com/download",
            r"^\d+-simple\.txt$",
        ),
        # Test with only filename*= (no regular filename) - should fall back to URL
        (
            {"content-disposition": "attachment; filename*=ISO-8859-1'en'%A3%20rates"},
            "https://files.example.org/data",
            r"^\d+-files\.example\.org$",
        ),
        # Test filename*= with content-type - should fall back to URL + extension
        (
            {"content-disposition": "attachment; filename*=UTF-8''document%2Epdf", "content-type": "application/pdf"},
            "https://docs.example.com/report",
            r"^\d+-docs\.example\.com\.pdf$",
        ),
        # Test without content-disposition, with hostname and content-type
        ({"content-type": "image/jpeg"}, "https://images.example.com/photo", r"^\d+-images\.example\.com\.jpg$"),
        # Test with content-disposition containing special characters
        (
            {"content-disposition": 'inline; filename="report (final).xlsx"'},
            "https://example.com/reports",
            r"^\d+-report \(final\)\.xlsx$",
        ),
        # Test with PNG content type
        ({"content-type": "image/png"}, "https://cdn.example.com/assets", r"^\d+-cdn\.example\.com\.png$"),
    ],
)
@patch("notte_core.utils.raw_file.time.time")
def test_get_filename_patterns(mock_time, headers, url, expected_filename_pattern):
    # Mock time.time() to return a consistent timestamp
    mock_time.return_value = 1234567890.123

    result = get_filename(headers, url)

    # Check that the result matches the expected pattern
    assert re.match(expected_filename_pattern, result), f"Expected pattern {expected_filename_pattern}, got {result}"

    # Verify timestamp is included
    assert result.startswith("1234567890-")
