"""`observe()` offers the link inside a clickable card, not only the card.

Search results are often cards with a pointer cursor around an image, a title link and a rating. The card
was offered as a generic clickable (`M`) and the link inside it was not, as a link nested in a highlighted
element was not a distinct interaction. Clicking the card only works when the page wired a handler to it,
and not always to the point clicked: the link is the one control that surely goes to the result.
"""

import pytest
from notte_browser.session import NotteSession
from patchright.async_api import Route

BASE_URL = "https://cards.notte.test"

RESULTS = """
<style>.card { cursor: pointer; width: 300px; border: 1px solid #ccc; padding: 8px }</style>
<h1>Results</h1>
<div class="card">
  <img alt="" width="100" height="60" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
  <a href="/recipe">Pancakes</a>
  <span>4.7/5</span>
</div>
"""


async def _serve(route: Route) -> None:
    body = RESULTS if route.request.url.endswith("/results") else "<h1>Pancakes recipe</h1>"
    await route.fulfill(body=body, content_type="text/html")


@pytest.mark.asyncio
async def test_the_link_inside_a_clickable_card_is_offered() -> None:
    async with NotteSession(headless=True) as session:
        await session.window.page.route(f"{BASE_URL}/**", _serve)
        _ = await session.window.page.goto(f"{BASE_URL}/results")
        observation = await session.aobserve()

        actions = [(action.id, action.text_label) for action in observation.space.interaction_actions]
        assert actions == [("M1", "Pancakes 4.7/5"), ("L1", "Pancakes")]

        _ = await session.aexecute(type="click", id="L1")
        assert session.window.page.url == f"{BASE_URL}/recipe"


# an image map: its `<area href>` hotspots have no box of their own, they are regions of the image
IMAGE_MAP = """
<style>.card { cursor: pointer; width: 300px; border: 1px solid #ccc; padding: 8px }</style>
<h1>Floor plan</h1>
<div class="card" onclick="document.title = 'card'">
  <img alt="Plan" width="200" height="100" usemap="#plan"
    src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
  <map name="plan">
    <area shape="rect" coords="0,0,100,100" href="/kitchen" alt="Kitchen">
    <area shape="circle" coords="150,50,40" href="/garden" alt="Garden">
  </map>
  <map name="unused"><area shape="rect" coords="0,0,10,10" href="/nowhere" alt="Nowhere"></map>
</div>
"""


async def _serve_map(route: Route) -> None:
    body = IMAGE_MAP if route.request.url.endswith("/plan") else "<h1>Room</h1>"
    await route.fulfill(body=body, content_type="text/html")


@pytest.mark.asyncio
async def test_the_areas_of_an_image_map_are_offered() -> None:
    async with NotteSession(headless=True) as session:
        await session.window.page.route(f"{BASE_URL}/**", _serve_map)
        _ = await session.window.page.goto(f"{BASE_URL}/plan")
        observation = await session.aobserve()

        links = {
            action.text_label or action.accessible_name: action.id
            for action in observation.space.interaction_actions
            if action.id.startswith("L")
        }
        assert list(links) == ["Kitchen", "Garden"]

        result = await session.aexecute(type="click", id=links["Garden"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/garden"
