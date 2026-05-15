import pytest
from notte_browser.session import NotteSession


@pytest.mark.asyncio
async def test_headless_aspect_ratio_sets_browser_viewport() -> None:
    async with NotteSession(headless=True, aspect_ratio="16:9") as session:
        viewport = await session.window.page.evaluate("[window.innerWidth, window.innerHeight]")

    assert viewport == [1280, 720]
