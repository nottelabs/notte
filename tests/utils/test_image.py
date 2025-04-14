from notte_core.utils.image import construct_image_url


def test_construct_image_url() -> None:
    base_url = "https://www.hbs.edu/news/articles/Pages/awa-ambra-seck-profile-2024.aspx"

    # Different types of image sources
    cases = [
        "/news/PublishingImages/image.jpg",  # Absolute path from root
        "image.jpg",  # Relative to current page
        "../images/image.jpg",  # Relative with parent directory
        "https://cdn.example.com/image.jpg",  # Full URL
        "//cdn.example.com/image.jpg",  # Protocol-relative URL
        "/~/media/mckinsey/featured%20insights/charting%20the%20path%20to%20the%20next%20normal",
    ]
    expected_results = [
        "https://www.hbs.edu/news/PublishingImages/image.jpg",
        "https://www.hbs.edu/news/articles/Pages/image.jpg",
        "https://www.hbs.edu/news/articles/images/image.jpg",
        "https://cdn.example.com/image.jpg",
        "https://cdn.example.com/image.jpg",
        "https://www.hbs.edu/~/media/mckinsey/featured%20insights/charting%20the%20path%20to%20the%20next%20normal",
    ]

    for src, expected in zip(cases, expected_results):
        result = construct_image_url(base_url, src)
        assert result == expected, f"Failed for case: {src} ({result} != {expected})"
