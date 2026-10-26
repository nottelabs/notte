"""`observe()` offers the areas of an image map wherever the page shows them.

An `<area href>` has no box of its own: it is a region of the image that uses its map. Its box is the bounds of
its shape on that image, and it is offered when the page hits it at a point of its shape. A polygon's center
can be outside it, and a `default` area is under the areas before it. Its coords are in the image's CSS pixels,
which a transform scales on screen. A map can be used by several images, of which the one in view is the one
the user sees. Maps are page content: many areas, or a polygon with many points, must not slow down or break
the build.
"""

import json

import pytest
from notte_browser.dom.parsing import DOM_TREE_JS
from notte_browser.session import NotteSession
from patchright.async_api import Route

BASE_URL = "https://maps.notte.test"
# a 1 x 1 image: an area's coords are in the CSS pixels of the image's box, whatever its natural size
GIF = "data:image/gif;base64,R0lGODlhAQABAAAAACw="

SHAPES = f"""
<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}">
<map name="plan">
  <area shape="poly" coords="0,0,100,0,100,20,20,20,20,100,0,100" href="/hall" alt="Hall">
  <area shape="rect" coords="80,30,120,70" href="/middle" alt="Middle">
  <area shape="default" href="/rest" alt="Rest">
</map>
"""

SCALED = f"""
<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}" style="transform: scale(2); transform-origin: 0 0">
<map name="plan">
  <area shape="rect" coords="0,0,100,100" href="/left" alt="Left">
  <area shape="rect" coords="100,0,200,100" href="/right" alt="Right">
</map>
"""

TWO_IMAGES = f"""
<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}">
<div style="height: 3000px"></div>
<img alt="Plan again" width="200" height="100" usemap="#plan" src="{GIF}">
<map name="plan">
  <area shape="rect" coords="0,0,100,100" href="/left" alt="Left">
  <area shape="rect" coords="100,0,200,100" href="/right" alt="Right">
</map>
"""

# only the top 20 pixels of the image are in the viewport
EDGE_OF_VIEW = f"""
<div style="height: calc(100vh - 20px)"></div>
<img alt="Plan" width="200" height="400" usemap="#plan" src="{GIF}" style="display: block">
<map name="plan"><area shape="rect" coords="0,0,200,400" href="/room" alt="Room"></map>
"""

# a polygon with 200,000 points along its bottom edge
LONG_POLYGON = f"""
<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}">
<map name="plan"><area shape="poly" href="/room" alt="Room"></map>
<script>
  const points = [0, 0, 200, 0];
  for (let i = 0; i < 200000; i++) points.push(200 - i / 1000, 100);
  document.querySelector("area").setAttribute("coords", points.join(","));
</script>
"""


def _serve(page: str):
    async def serve(route: Route) -> None:
        body = page if route.request.url.endswith("/plan") else "<h1>Room</h1>"
        await route.fulfill(body=body, content_type="text/html")

    return serve


async def _offered_areas(session: NotteSession, page: str, scroll_to_end: bool = False) -> dict[str, str]:
    await session.window.page.route(f"{BASE_URL}/**", _serve(page))
    _ = await session.window.page.goto(f"{BASE_URL}/plan")
    if scroll_to_end:
        await session.window.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    observation = await session.aobserve()
    return {
        action.text_label or action.accessible_name or "": action.id
        for action in observation.space.interaction_actions
        if action.id.startswith("L")
    }


@pytest.mark.asyncio
async def test_areas_hit_away_from_the_center_of_their_box_are_offered() -> None:
    """The hall's center is outside its L shape, and the middle covers the center of the `default` area."""
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, SHAPES)
        assert list(areas) == ["Hall", "Middle", "Rest"]

        result = await session.aexecute(type="click", id=areas["Hall"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/hall"


@pytest.mark.asyncio
async def test_the_areas_of_a_scaled_image_are_offered() -> None:
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, SCALED)
        assert list(areas) == ["Left", "Right"]

        result = await session.aexecute(type="click", id=areas["Right"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/right"


@pytest.mark.asyncio
async def test_the_areas_of_the_image_in_view_are_offered() -> None:
    """Two images use the map: the first is above the viewport, the second in it."""
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, TWO_IMAGES, scroll_to_end=True)
        assert list(areas) == ["Left", "Right"]

        result = await session.aexecute(type="click", id=areas["Right"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/right"


@pytest.mark.asyncio
async def test_an_area_cut_by_the_edge_of_the_viewport_is_offered() -> None:
    """The points tried are in the part of the area's box that is in view."""
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, EDGE_OF_VIEW)
        assert list(areas) == ["Room"]


@pytest.mark.asyncio
async def test_a_polygon_with_many_points_is_offered() -> None:
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, LONG_POLYGON)
        assert list(areas) == ["Room"]


@pytest.mark.asyncio
async def test_the_images_of_the_maps_are_found_once_per_build() -> None:
    """The images that use maps are looked up once, not once per area."""
    areas = "".join(f'<area shape="rect" coords="{i},0,{i + 1},100" href="/{i}" alt="{i}">' for i in range(0, 200, 2))
    page = f'<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}"><map name="plan">{areas}</map>'
    async with NotteSession(headless=True) as session:
        browser_page = session.window.page
        await browser_page.route(f"{BASE_URL}/**", _serve(page))
        _ = await browser_page.goto(f"{BASE_URL}/plan")
        # counted in the page world, where the DOM build reads `Document.prototype.querySelectorAll` when it calls it
        await browser_page.evaluate(
            """() => {
                const native = Document.prototype.querySelectorAll;
                window.imageLookups = 0;
                Document.prototype.querySelectorAll = function (selector) {
                    if (selector === "img[usemap]") window.imageLookups++;
                    return native.call(this, selector);
                };
            }""",
            isolated_context=False,
        )
        args = {
            "highlight_elements": True,
            "focus_element": -1,
            "viewport_expansion": 0,
            "enable_pointer_elements": True,
        }
        payload = json.loads(await browser_page.evaluate(DOM_TREE_JS, args, isolated_context=False))

        offered = [
            node for node in payload["map"].values() if node.get("tagName") == "area" and "highlightIndex" in node
        ]
        assert len(offered) == 100
        assert await browser_page.evaluate("window.imageLookups", isolated_context=False) == 1
