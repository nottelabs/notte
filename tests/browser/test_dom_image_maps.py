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

# an L of two 4-pixel strips: no point of a grid over its box is in it
NARROW = f"""
<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}">
<map name="plan"><area shape="poly" coords="0,0,200,0,200,4,4,4,4,100,0,100" href="/corridor" alt="Corridor"></map>
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

# both images are in view, but the bottom of the first, where "Bottom" is, is far below the viewport
SHARED_IN_VIEW = f"""
<img alt="Tall plan" width="200" height="4000" usemap="#plan" src="{GIF}" style="position: absolute; top: 50vh; left: 0">
<img alt="Plan" width="200" height="4000" usemap="#plan" src="{GIF}" style="position: absolute; top: calc(100vh - 4000px); left: 300px">
<map name="plan">
  <area shape="rect" coords="0,0,200,40" href="/top" alt="Top">
  <area shape="rect" coords="0,3960,200,4000" href="/bottom" alt="Bottom">
</map>
"""

# two images in view use the map, and a banner covers the first
COVERED = f"""
<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}" style="display: block">
<div style="position: absolute; top: 0; left: 0; width: 300px; height: 150px; background: white">Banner</div>
<img alt="Plan again" width="200" height="100" usemap="#plan" src="{GIF}" style="display: block; margin-top: 100px">
<map name="plan"><area shape="rect" coords="0,0,200,100" href="/room" alt="Room"></map>
"""

# an image turned or flipped by its own transform (see the test), whose areas move with it
TRANSFORMED = f"""
<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}" style="display: block; margin: 100px; transform: {{}}">
<map name="plan">
  <area shape="rect" coords="0,0,100,100" href="/left" alt="Left">
  <area shape="rect" coords="100,0,200,100" href="/right" alt="Right">
</map>
"""

# the map is in a wrapper that clips it, the image is not
CLIPPED_MAP = f"""
<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}">
<div style="height: 0; overflow: hidden">
  <map name="plan"><area shape="rect" coords="0,0,200,100" href="/room" alt="Room"></map>
</div>
"""

# a map named by its `id` only, which Chromium matches too
BY_ID = f"""
<img alt="Plan" width="200" height="100" usemap="#plan" src="{GIF}">
<map id="plan"><area shape="rect" coords="0,0,200,100" href="/room" alt="Room"></map>
"""

# only the top 20 pixels of the image are in the viewport
BELOW_VIEW = f"""
<div style="height: calc(100vh - 20px)"></div>
<img alt="Plan" width="200" height="400" usemap="#plan" src="{GIF}" style="display: block">
<map name="plan"><area shape="rect" coords="0,0,200,400" href="/room" alt="Room"></map>
"""

# a 1,000 pixel high image, scrolled to its last 50 pixels (see the test)
ABOVE_VIEW = f"""
<img alt="Plan" width="200" height="1000" usemap="#plan" src="{GIF}" style="display: block">
<div style="height: 3000px"></div>
<map name="plan"><area shape="default" href="/room" alt="Room"></map>
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


async def _offered_areas(session: NotteSession, page: str, scroll_y: int | None = None) -> dict[str, str]:
    """The links offered on the page, scrolled to `scroll_y` (the end of the page when -1)."""
    await session.window.page.route(f"{BASE_URL}/**", _serve(page))
    _ = await session.window.page.goto(f"{BASE_URL}/plan")
    if scroll_y is not None:
        await session.window.page.evaluate(
            "(y) => window.scrollTo(0, y < 0 ? document.body.scrollHeight : y)", scroll_y
        )
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
async def test_a_narrow_polygon_is_offered() -> None:
    """Points near the polygon's corners are tried too."""
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, NARROW)
        assert list(areas) == ["Corridor"]

        result = await session.aexecute(type="click", id=areas["Corridor"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/corridor"


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
        areas = await _offered_areas(session, TWO_IMAGES, scroll_y=-1)
        assert list(areas) == ["Left", "Right"]

        result = await session.aexecute(type="click", id=areas["Right"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/right"


@pytest.mark.asyncio
async def test_each_area_takes_the_image_that_shows_it() -> None:
    """Two images in view use the map: "Bottom" is out of view on the first and in view on the second."""
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, SHARED_IN_VIEW)
        assert sorted(areas) == ["Bottom", "Top"]

        result = await session.aexecute(type="click", id=areas["Bottom"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/bottom"


@pytest.mark.asyncio
async def test_an_area_takes_the_image_that_is_not_covered() -> None:
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, COVERED)
        assert list(areas) == ["Room"]

        result = await session.aexecute(type="click", id=areas["Room"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/room"


@pytest.mark.asyncio
@pytest.mark.parametrize("transform", ["scaleX(-1)", "rotate(90deg)", "rotate(180deg) scale(1.5)"])
async def test_the_areas_of_a_turned_or_flipped_image_are_offered(transform: str) -> None:
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, TRANSFORMED.format(transform))
        assert sorted(areas) == ["Left", "Right"]

        result = await session.aexecute(type="click", id=areas["Left"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/left"


@pytest.mark.asyncio
async def test_the_areas_of_a_clipped_map_are_offered_on_their_image() -> None:
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, CLIPPED_MAP)
        assert list(areas) == ["Room"]

        result = await session.aexecute(type="click", id=areas["Room"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/room"


@pytest.mark.asyncio
async def test_the_areas_of_a_map_named_by_its_id_are_offered() -> None:
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, BY_ID)
        assert list(areas) == ["Room"]

        result = await session.aexecute(type="click", id=areas["Room"])
        assert result.success, result.message
        assert session.window.page.url == f"{BASE_URL}/room"


@pytest.mark.asyncio
@pytest.mark.parametrize(("page", "scroll_y"), [(BELOW_VIEW, 0), (ABOVE_VIEW, 950)])
async def test_an_area_cut_by_the_edge_of_the_viewport_is_offered(page: str, scroll_y: int) -> None:
    """The points tried are in the part of the area's box that is in view."""
    async with NotteSession(headless=True) as session:
        areas = await _offered_areas(session, page, scroll_y=scroll_y)
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
