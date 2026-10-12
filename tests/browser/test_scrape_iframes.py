import re
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from patchright.async_api import Route

import notte

PAGES = {
    "https://example.test/": (
        "<h1>Main</h1>"
        '<iframe src="https://first.test/"></iframe>'
        "<p>between</p>"
        '<iframe src="https://second.test/"></iframe>'
    ),
    "https://first.test/": '<p>first frame</p><iframe src="https://nested.test/"></iframe>',
    "https://second.test/": "<p>second frame</p>",
    "https://nested.test/": "<p>nested frame</p>",
    "https://inserted.test/": "<p>inserted frame</p>",
}


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async def serve(route: Route) -> None:
        body = PAGES.get(route.request.url)
        if body is None:
            await route.abort()
        else:
            await route.fulfill(body=body, content_type="text/html")

    async with notte.Session(headless=True) as session:
        await session.window.page.route("**/*", serve)
        _ = await session.window.page.goto("https://example.test/", wait_until="load")
        yield session


def _iframe_urls(markdown: str) -> list[str]:
    return re.findall(r"^IFRAME (\S+):$", markdown, flags=re.MULTILINE)


@pytest.mark.asyncio
async def test_iframes_are_appended_in_document_order(session: NotteSession) -> None:
    for _ in range(3):
        markdown = await session.ascrape()

        assert _iframe_urls(markdown) == ["https://first.test/", "https://nested.test/", "https://second.test/"]
        assert markdown.index("first frame") < markdown.index("nested frame") < markdown.index("second frame")


@pytest.mark.asyncio
async def test_iframe_inserted_later_is_appended_at_its_document_position(session: NotteSession) -> None:
    page = session.window.page
    _ = await page.evaluate(
        """() => new Promise(resolve => {
            const iframe = document.createElement("iframe");
            iframe.onload = resolve;
            iframe.src = "https://inserted.test/";
            document.body.prepend(iframe);
        })"""
    )

    markdown = await session.ascrape()

    assert _iframe_urls(markdown) == [
        "https://inserted.test/",
        "https://first.test/",
        "https://nested.test/",
        "https://second.test/",
    ]


@pytest.mark.asyncio
async def test_iframe_in_shadow_root_takes_its_host_position(session: NotteSession) -> None:
    page = session.window.page
    _ = await page.evaluate(
        """() => new Promise(resolve => {
            const host = document.createElement("div");
            document.querySelector("p").before(host);
            const iframe = document.createElement("iframe");
            iframe.onload = resolve;
            iframe.src = "https://inserted.test/";
            host.attachShadow({ mode: "open" }).append(iframe);
        })"""
    )

    markdown = await session.ascrape()

    assert _iframe_urls(markdown) == [
        "https://first.test/",
        "https://nested.test/",
        "https://inserted.test/",
        "https://second.test/",
    ]
