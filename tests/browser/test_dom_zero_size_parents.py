"""`observe()` keeps the content of a zero-size element below the fold.

An inline `<li>` around a floated link (a common pager markup), or an inline element around a positioned
one, has an empty box, while its children are laid out elsewhere. Below the viewport, the DOM build used to
drop such an element with its whole subtree, so the link was missing from the snapshot, both as a
node and as text, while the text after it was kept.
"""

from urllib.parse import quote

import pytest
from notte_browser.session import NotteSession

SPACER = '<div style="height: 2000px">Top of the page</div>'
FOOTER = "<footer>Footer text</footer>"

PAGES = {
    "inline parent of a floated link": """
        <nav><ul><li style="display: inline"><a href="/page/2/" style="float: right">Next</a></li></ul></nav>
    """,
    "inline parent of a positioned link": """
        <p><span><a href="/page/2/" style="position: absolute">Next</a></span></p>
    """,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("markup", PAGES.values(), ids=PAGES.keys())
async def test_offscreen_link_in_a_zero_size_parent_is_in_the_snapshot(markup: str) -> None:
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(SPACER + markup + FOOTER)}")
        _ = await session.aobserve()

        nodes = session.snapshot.dom_node.flatten()
        links = [node for node in nodes if node.attributes is not None and node.attributes.href == "/page/2/"]
        texts = [node.text for node in nodes]
        assert len(links) == 1
        assert links[0].inner_text() == "Next"
        assert "Next" in texts
        assert "Footer text" in texts


@pytest.mark.asyncio
async def test_offscreen_content_that_is_not_rendered_stays_out() -> None:
    # the cells of a `hidden="until-found"` row are laid out but not rendered (a collapsed table, as
    # MediaWiki renders them: the row is a zero-height block)
    hidden_row = """<table>
        <tr><th>Header</th></tr>
        <tr hidden="until-found" style="display: block; width: 0; height: 0"><td>Hidden cell</td></tr>
    </table>"""
    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto(f"data:text/html,{quote(SPACER + hidden_row + FOOTER)}")
        _ = await session.aobserve()

        texts = [node.text for node in session.snapshot.dom_node.flatten()]
        assert "Header" in texts
        assert "Hidden cell" not in texts
        assert "Footer text" in texts
