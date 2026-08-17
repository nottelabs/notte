import json
import subprocess
import sys
from types import SimpleNamespace

from notte_browser.scraping.markdown import MainContentScrapingPipe
from notte_sdk.types import ScrapeParams


def _snapshot(html: str) -> SimpleNamespace:
    return SimpleNamespace(html_content=html, metadata=SimpleNamespace(url="https://example.com"))


def test_main_content_prefers_articles_inside_main() -> None:
    result = MainContentScrapingPipe.forward(
        _snapshot(
            "<html><body><header>nav</header><main><p>intro</p>"
            '<article><h1>First</h1><a href="https://example.com/first">Read</a></article>'
            "<article><h2>Second</h2></article></main><article>outside</article></body></html>"
        ),  # type: ignore[arg-type]
        ScrapeParams(only_main_content=True, scrape_links=True),
    )

    assert "First" in result
    assert "Second" in result
    assert "https://example.com/first" in result
    assert "intro" not in result
    assert "outside" not in result
    assert "nav" not in result


def test_main_content_uses_deepest_conventional_content_id() -> None:
    result = MainContentScrapingPipe.forward(
        _snapshot('<div id="main">outer<div id="contents"><h1>Deep content</h1></div></div>'),  # type: ignore[arg-type]
        ScrapeParams(only_main_content=True),
    )

    assert "Deep content" in result
    assert "outer" not in result


def test_main_content_removes_hidden_and_configured_tags_but_keeps_text() -> None:
    result = MainContentScrapingPipe.forward(
        _snapshot(
            '<main><p style="display: none">secret</p><p style="visibility:hidden">also secret</p>'
            "<p>visible <em>emphasis</em></p>"
            '<a href="https://example.com">link text</a><img src="image.png" alt="image alt"></main>'
        ),  # type: ignore[arg-type]
        ScrapeParams(only_main_content=True, ignored_tags=["em"], scrape_links=False, scrape_images=False),
    )

    assert "visible emphasis" in result
    assert "link text" in result
    assert "secret" not in result
    assert "https://example.com" not in result
    assert "image alt" not in result


def test_main_content_falls_back_for_document_without_landmarks() -> None:
    result = MainContentScrapingPipe.forward(
        _snapshot("<html><body><div><h1>Fallback title</h1><p>Fallback body with enough text.</p></div></body></html>"),  # type: ignore[arg-type]
        ScrapeParams(only_main_content=True),
    )

    assert "Fallback title" in result
    assert "Fallback body" in result


def test_main_content_preserves_image_behavior_without_global_config_mutation() -> None:
    snapshot = _snapshot('<main><img src="https://example.com/image.png" alt="image alt"></main>')
    params = ScrapeParams(only_main_content=True, scrape_images=True)

    markdown_image = MainContentScrapingPipe.forward(snapshot, params)  # type: ignore[arg-type]
    alt_only = MainContentScrapingPipe.forward(snapshot, params, images_to_alt=True)  # type: ignore[arg-type]

    assert "https://example.com/image.png" in markdown_image
    assert "image alt" in alt_only
    assert "https://example.com/image.png" not in alt_only


def test_main_content_handles_malformed_html() -> None:
    result = MainContentScrapingPipe.forward(
        _snapshot("<main><h1>Broken<p>Still readable"),  # type: ignore[arg-type]
        ScrapeParams(only_main_content=True),
    )

    assert "Broken" in result
    assert "Still readable" in result


def test_dense_dom_peak_memory_regression() -> None:
    script = """
import json
import resource
import sys
from types import SimpleNamespace
from notte_browser.scraping.markdown import MainContentScrapingPipe
from notte_sdk.types import ScrapeParams

baseline = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
html = "<main>" + "<i>x</i>" * 524_288 + "</main>"
result = MainContentScrapingPipe.forward(
    SimpleNamespace(html_content=html, metadata=SimpleNamespace(url="https://example.com")),
    ScrapeParams(only_main_content=True),
)
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
units_per_mib = 1024 * 1024 if sys.platform == "darwin" else 1024
print(json.dumps({"delta_mib": (peak - baseline) / units_per_mib, "output_chars": len(result)}))
"""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    measurement = json.loads(completed.stdout)

    assert measurement["output_chars"] > 0
    assert measurement["delta_mib"] < 350
