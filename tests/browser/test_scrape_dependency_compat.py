from notte_browser.scrape import VisibleMarkdownConverter


def test_visible_markdown_converter_drops_hidden_content_and_keeps_markdown() -> None:
    result = VisibleMarkdownConverter().convert(
        "<html><body><h1>Title</h1>"
        '<p style="display: none">hidden one</p><div style="visibility:hidden"><p>hidden two</p></div>'
        '<p>Some <strong>bold</strong> text and a <a href="https://example.com/x">link</a>.</p>'
        "<ul><li>first</li><li>second</li></ul></body></html>"
    )

    assert "Title\n=====" in result
    assert "**bold**" in result
    assert "[link](https://example.com/x)" in result
    assert "* first" in result
    assert "* second" in result
    assert "hidden" not in result
