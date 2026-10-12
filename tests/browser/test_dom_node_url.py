import pytest
from notte_core.browser.dom_tree import ComputedDomAttributes, DomNode, NodeSelectors
from notte_core.browser.node_type import NodeRole, NodeType
from patchright.async_api import Route

import notte


def _node(notte_selector: str | None) -> DomNode:
    selectors = NodeSelectors(
        css_selector="",
        xpath_selector="",
        in_iframe=False,
        in_shadow_root=False,
        notte_selector=notte_selector,
        iframe_parent_css_selectors=[],
    )
    return DomNode(
        id="B1",
        role=NodeRole.BUTTON,
        text="",
        type=NodeType.INTERACTION,
        children=[],
        attributes=None,
        computed_attributes=ComputedDomAttributes(selectors=selectors),
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a/b",
        "http://localhost:8080/",
        "https://example.com/watch?t=10:30",
        "about:blank",
        "data:text/html,<p>hi</p>",
    ],
)
@pytest.mark.parametrize("depth", [1, 3])
def test_get_url_strips_the_element_hashes(url: str, depth: int) -> None:
    hashes = ":".join(f"{h}:-{h}" for h in range(123456789, 123456789 + depth))

    assert _node(f"{url}:{hashes}").get_url() == url


@pytest.mark.parametrize("notte_selector", [None, ""])
def test_get_url_without_notte_selector(notte_selector: str | None) -> None:
    assert _node(notte_selector).get_url() is None


@pytest.mark.asyncio
async def test_get_url_on_parsed_page() -> None:
    url = "https://example.test:8443/path/page.html?q=1"

    async def serve(route: Route) -> None:
        await route.fulfill(body="<main><div><form><button>Go</button></form></div></main>", content_type="text/html")

    async with notte.Session(headless=True) as session:
        await session.window.page.route("**/*", serve)
        _ = await session.window.page.goto(url)
        snapshot = await session.window.snapshot(screenshot=False)

    nodes = snapshot.dom_node.flatten(keep_filter=lambda node: node.computed_attributes.selectors is not None)
    assert len(nodes) > 0
    assert {node.get_url() for node in nodes} == {url}
