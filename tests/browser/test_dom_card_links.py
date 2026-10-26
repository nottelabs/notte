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
