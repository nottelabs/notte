import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace

from notte_browser.scraping.markdown import page_markdown
from notte_sdk.types import ScrapeParams

# a window without iframes
_FRAME = SimpleNamespace(url="https://example.com", child_frames=[])
_WINDOW = SimpleNamespace(page=SimpleNamespace(url=_FRAME.url, main_frame=_FRAME))


def _snapshot(html: str) -> SimpleNamespace:
    return SimpleNamespace(html_content=html, metadata=SimpleNamespace(url="https://example.com"))


def _markdown(snapshot: SimpleNamespace, params: ScrapeParams) -> str:
    return asyncio.run(page_markdown(_WINDOW, snapshot, params))  # type: ignore[arg-type]


def test_main_content_prefers_articles_inside_main() -> None:
    result = _markdown(
        _snapshot(
            "<html><body><header>nav</header><main><p>intro</p>"
            '<article><h1>First</h1><a href="https://example.com/first">Read</a></article>'
            "<article><h2>Second</h2></article></main><article>outside</article></body></html>"
        ),
        ScrapeParams(only_main_content=True, scrape_links=True),
    )

    assert "First" in result
    assert "Second" in result
    assert "https://example.com/first" in result
    assert "intro" not in result
    assert "outside" not in result
    assert "nav" not in result


def test_main_content_uses_deepest_conventional_content_id() -> None:
    result = _markdown(
        _snapshot('<div id="main">outer<div id="contents"><h1>Deep content</h1></div></div>'),
        ScrapeParams(only_main_content=True),
    )

    assert "Deep content" in result
    assert "outer" not in result


def test_main_content_removes_hidden_and_configured_tags_but_keeps_text() -> None:
    result = _markdown(
        _snapshot(
            '<main><p style="display: none">secret</p><p style="visibility:hidden">also secret</p>'
            "<p>visible <em>emphasis</em></p>"
            '<a href="https://example.com">link text</a><img src="image.png" alt="image alt"></main>'
        ),
        ScrapeParams(only_main_content=True, ignored_tags=["em"], scrape_links=False, scrape_images=False),
    )

    assert "visible emphasis" in result
    assert "link text" in result
    assert "secret" not in result
    assert "https://example.com" not in result
    assert "image alt" not in result


def test_main_content_falls_back_for_document_without_landmarks() -> None:
    result = _markdown(
        _snapshot("<html><body><div><h1>Fallback title</h1><p>Fallback body with enough text.</p></div></body></html>"),
        ScrapeParams(only_main_content=True),
    )

    assert "Fallback title" in result
    assert "Fallback body" in result


def test_main_content_keeps_images_when_asked() -> None:
    markdown = _markdown(
        _snapshot('<main><img src="https://example.com/image.png" alt="image alt"></main>'),
        ScrapeParams(only_main_content=True, scrape_images=True),
    )

    assert "![image alt](https://example.com/image.png)" in markdown


def test_full_page_keeps_navigation_and_hides_hidden_content() -> None:
    markdown = _markdown(
        _snapshot('<header>nav</header><main><p>body</p><p style="display: none">secret</p></main>'),
        ScrapeParams(),
    )

    assert "nav" in markdown
    assert "body" in markdown
    assert "secret" not in markdown


def test_main_content_handles_malformed_html() -> None:
    result = _markdown(
        _snapshot("<main><h1>Broken<p>Still readable"),
        ScrapeParams(only_main_content=True),
    )

    assert "Broken" in result
    assert "Still readable" in result


def test_main_content_handles_comments_when_stripping_tags() -> None:
    result = _markdown(
        _snapshot("<main><!-- marker --><p>visible <em>emphasis</em></p></main>"),
        ScrapeParams(only_main_content=True, ignored_tags=["em"]),
    )

    assert "visible emphasis" in result


def test_dense_dom_peak_memory_regression() -> None:
    script = """
import json
import resource
import sys
from types import SimpleNamespace
import asyncio
from notte_browser.scraping.markdown import page_markdown
from notte_sdk.types import ScrapeParams

baseline = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
html = "<main>" + "<i>x</i>" * 524_288 + "</main>"
result = asyncio.run(page_markdown(
    SimpleNamespace(page=SimpleNamespace(url="", main_frame=SimpleNamespace(url="", child_frames=[]))),
    SimpleNamespace(html_content=html, metadata=SimpleNamespace(url="https://example.com")),
    ScrapeParams(only_main_content=True),
))
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
