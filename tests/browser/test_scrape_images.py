from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
import pytest_asyncio
from notte_browser.session import NotteSession
from notte_core.data.space import ImageCategory
from patchright.async_api import Route

import notte

URL = "https://example.test/dir/page.html"


@pytest_asyncio.fixture(loop_scope="function")
async def open_page() -> AsyncIterator[Callable[[str], Any]]:
    """Serve `html` at URL (every other request is aborted) and return the session."""
    async with notte.Session(headless=True) as session:

        async def open_page(html: str) -> NotteSession:
            async def serve(route: Route) -> None:
                if route.request.url == URL:
                    await route.fulfill(body=html, content_type="text/html")
                else:
                    await route.abort()

            await session.window.page.route("**/*", serve)
            _ = await session.window.page.goto(URL)
            return session

        yield open_page


@pytest.mark.asyncio
async def test_favicon_defaults_to_the_origin(open_page: Callable[[str], Any]) -> None:
    session: NotteSession = await open_page("<p>no icon</p>")

    images = await session.ascrape(only_images=True)

    assert images[0].category == ImageCategory.FAVICON
    assert images[0].url == "https://example.test/favicon.ico"


@pytest.mark.asyncio
async def test_favicon_uses_the_icon_link(open_page: Callable[[str], Any]) -> None:
    session: NotteSession = await open_page(
        '<head><link rel="apple-touch-icon" href="/touch.png"><link rel="mask-icon" href="/mask.svg">'
        '<link rel="icon" href=""><link rel="Shortcut Icon" href="../static/icon.png"><link rel="icon" href="/other.png"></head><p>icon</p>'
    )

    images = await session.ascrape(only_images=True)

    assert images[0].category == ImageCategory.FAVICON
    assert images[0].url == "https://example.test/static/icon.png"


SELECTOR_PAGE = (
    '<header><img class="logo-icon" src="/logo.png" alt="logo">'
    '<svg width="20" height="20"><rect width="20" height="20"/></svg></header>'
    '<section id="gallery"><img src="/photo.png" alt="A photo" width="300" height="200">'
    '<svg width="300" height="200"><rect width="300" height="200"/></svg></section>'
)


@pytest.mark.asyncio
async def test_images_with_selector_are_classified_from_the_selected_elements(open_page: Callable[[str], Any]) -> None:
    session: NotteSession = await open_page(SELECTOR_PAGE)

    images = await session.ascrape(only_images=True, selector="#gallery")

    assert [(image.category, image.url) for image in images[1:]] == [
        (ImageCategory.CONTENT_IMAGE, "https://example.test/photo.png"),
        (ImageCategory.SVG_CONTENT, '<svg width="300" height="200"><rect width="300" height="200"></rect></svg>'),
    ]


@pytest.mark.asyncio
async def test_images_without_selector(open_page: Callable[[str], Any]) -> None:
    session: NotteSession = await open_page(SELECTOR_PAGE)

    images = await session.ascrape(only_images=True)

    assert [(image.category, image.url) for image in images[1:]] == [
        (ImageCategory.ICON, "https://example.test/logo.png"),
        (ImageCategory.SVG_ICON, None),
        (ImageCategory.CONTENT_IMAGE, "https://example.test/photo.png"),
        (ImageCategory.SVG_CONTENT, '<svg width="300" height="200"><rect width="300" height="200"></rect></svg>'),
    ]
