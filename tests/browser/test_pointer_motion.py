"""The pointer travels to an element before it is clicked, and moves over a page once after it has loaded
(`notte_browser.pointer`)."""

import random
import socket
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import closing
from unittest.mock import patch

import notte_browser.execution as execution_module
import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser import pointer
from notte_browser.driver import Page, evaluate_in_main_world
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction
from notte_core.config import config

RECORD = """<script>
window.moves = []; window.downs = []; window.overs = []; window.wheels = [];
addEventListener('wheel', e => { if (e.isTrusted) wheels.push(e.deltaY) }, { capture: true, passive: true });
addEventListener('mousemove', e => { if (e.isTrusted) moves.push([e.clientX, e.clientY]) }, true);
addEventListener('mousedown', e => { if (e.isTrusted) downs.push([e.target.id, e.clientX, e.clientY, moves.length]) }, true);
addEventListener('mouseover', e => {
  if (e.isTrusted && e.target.closest('a, button, input, canvas, iframe, .pointer')) overs.push(e.target.tagName)
}, true);
</script>"""

PAGES = {
    "/": f"""<html><body style="margin:0; height:2400px">
<button id="buy" style="position:absolute; left:600px; top:400px; width:120px; height:40px">Buy</button>
<button id="far" style="position:absolute; left:300px; top:2000px; width:100px; height:30px">Far</button>
<iframe id="frame" src="/inner" style="position:absolute; left:100px; top:100px; width:300px; height:200px; border:0">
</iframe>{RECORD}</body></html>""",
    "/inner": f"""<html><body style="margin:0">
<button id="inner" style="position:absolute; left:40px; top:60px; width:100px; height:30px">Inner</button>
{RECORD}</body></html>""",
    # controls all over the page, a canvas and a clickable div: the pointer must keep off them
    "/busy": f"""<html><body style="margin:0; height:3000px; font-size:20px">
{"".join(f'<a href="#{i}" style="display:inline-block; width:90px; margin:40px 60px">link {i}</a>' for i in range(30))}
<canvas width="300" height="150"></canvas><div class="pointer" style="cursor:pointer; height:80px">Card</div>
<button>Buy</button>{RECORD}</body></html>""",
    "/calm": f"""<html><body style="margin:0; height:3000px"><p>Plain text</p>{RECORD}</body></html>""",
}


@pytest_asyncio.fixture(loop_scope="function")
async def site() -> AsyncIterator[str]:
    async def page(request: web.Request) -> web.Response:
        return web.Response(text=PAGES[request.path], content_type="text/html")

    app = web.Application()
    for path in PAGES:
        app.router.add_get(path, page)
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        await web.SockSite(runner, server_socket).start()
        try:
            yield f"http://127.0.0.1:{server_socket.getsockname()[1]}"
        finally:
            await runner.cleanup()


@pytest.fixture
def pointer_motion() -> Iterator[None]:
    with patch.object(execution_module, "config", config.model_copy(update={"pointer_motion": True})):
        yield


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=800) as session:
        yield session


async def main_world(page: Page, expression: str) -> list[list[float | str]]:
    return await evaluate_in_main_world(page.main_frame, expression)


def inside(point: list[float | str], box: tuple[float, float, float, float]) -> bool:
    x, y = float(point[0]), float(point[1])
    return box[0] <= x <= box[0] + box[2] and box[1] <= y <= box[1] + box[3]


# --- paths --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(200))
def test_a_path_ends_exactly_on_its_target_and_stays_in_the_viewport(seed: int) -> None:
    rand = random.Random(seed)
    start = (rand.uniform(0, 1280), rand.uniform(0, 800))
    end = (rand.uniform(0, 1279), rand.uniform(0, 799))
    steps = rand.randint(*pointer.APPROACH_STEPS)
    path = pointer.curve(start, end, steps, rand, (1280, 800))
    assert len(path) == steps
    assert path[-1] == end
    assert all(0 <= x <= 1279 and 0 <= y <= 799 for x, y in path)


def test_a_path_bends_and_moves_towards_its_target() -> None:
    rand = random.Random(7)
    path = pointer.curve((100, 100), (700, 100), 20, rand)
    # it leaves the straight line between both ends
    assert max(abs(y - 100) for _, y in path) > 5
    # and gets closer to the target as it goes, jitter aside
    xs = [x for x, _ in path]
    assert all(b > a - 3 for a, b in zip(xs, xs[1:]))


@pytest.mark.parametrize("seed", range(200))
def test_the_click_point_is_inside_the_visible_part_of_the_element(seed: int) -> None:
    rand = random.Random(seed)
    box = pointer.Box(
        x=rand.uniform(-200, 1200), y=rand.uniform(-200, 700), width=rand.uniform(2, 400), height=rand.uniform(2, 200)
    )
    visible = pointer.visible_part(box, 1280, 800)
    if visible is None:
        assert box["x"] + box["width"] < 1 or box["x"] > 1279 or box["y"] + box["height"] < 1 or box["y"] > 799
        return
    x, y = pointer.point_in(visible, rand)
    assert max(box["x"], 0) <= x <= min(box["x"] + box["width"], 1280)
    assert max(box["y"], 0) <= y <= min(box["y"] + box["height"], 800)


def test_a_seed_gives_the_same_path() -> None:
    paths = [pointer.curve((10, 20), (500, 300), 18, random.Random(3)) for _ in range(2)]
    assert paths[0] == paths[1]


# --- clicks -------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("pointer_motion")
async def test_the_pointer_travels_to_the_element_before_the_click_lands(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    page = session.window.page
    _ = await evaluate_in_main_world(page.main_frame, "moves.length = 0")
    result = await session.aexecute(ClickAction(selector="#buy"), raise_on_failure=True)
    assert result.success
    downs = await main_world(page, "downs")
    assert [down[0] for down in downs] == ["buy"]
    moves = (await main_world(page, "moves"))[: int(downs[0][3])]
    assert len(moves) >= pointer.APPROACH_STEPS[0]
    buy = (600, 400, 120, 40)
    # the approach ends inside the element, where the click lands
    assert inside(moves[-2], buy) and inside(moves[-1], buy) and inside(downs[0][1:3], buy)
    assert not all(inside(move, buy) for move in moves)
    assert all(inside(move, (0, 0, 1280, 800)) for move in moves)


@pytest.mark.asyncio
@pytest.mark.usefixtures("pointer_motion")
async def test_an_element_out_of_view_is_scrolled_to_before_the_pointer_travels(
    session: NotteSession, site: str
) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    result = await session.aexecute(ClickAction(selector="#far"), raise_on_failure=True)
    assert result.success
    page = session.window.page
    downs = await main_world(page, "downs")
    assert [down[0] for down in downs] == ["far"]
    moves = (await main_world(page, "moves"))[: int(downs[-1][3])]
    assert len(moves) >= pointer.APPROACH_STEPS[0]
    assert all(inside(move, (0, 0, 1280, 800)) for move in moves)


@pytest.mark.asyncio
async def test_the_pointer_travels_into_a_frame(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    page = session.window.page
    locator = page.frame_locator("#frame").locator("#inner")
    point = await pointer.approach(page, locator, time_left_s=10, rand=random.Random(1))
    assert point is not None
    # the frame is at (100, 100) of the page, its button at (40, 60) of the frame
    assert inside(list(point), (140, 160, 100, 30))
    await locator.click()
    frame = page.frames[1]
    downs = await evaluate_in_main_world(frame, "downs")
    assert [down[0] for down in downs] == ["inner"]
    assert len(await evaluate_in_main_world(frame, "moves")) > 3


@pytest.mark.asyncio
async def test_a_hidden_element_is_not_approached(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    page = session.window.page
    await page.evaluate("() => { document.getElementById('buy').style.display = 'none' }")
    assert await pointer.approach(page, page.locator("#buy"), time_left_s=10) is None
    assert await main_world(page, "moves") == []


@pytest.mark.asyncio
async def test_no_approach_without_the_time_for_it(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    page = session.window.page
    assert await pointer.approach(page, page.locator("#buy"), time_left_s=pointer.APPROACH_S[0]) is None
    assert await main_world(page, "moves") == []


@pytest.mark.asyncio
async def test_without_pointer_motion_the_click_moves_once(session: NotteSession, site: str) -> None:
    assert not config.pointer_motion
    _ = await session.aexecute(type="goto", url=f"{site}/")
    page = session.window.page
    assert await main_world(page, "moves") == []
    _ = await session.aexecute(ClickAction(selector="#buy"), raise_on_failure=True)
    downs = await main_world(page, "downs")
    assert len(downs) == 1 and int(downs[0][3]) <= 1


# --- after a page load --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.usefixtures("pointer_motion")
async def test_the_pointer_moves_once_per_page_load_and_keeps_off_controls(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/busy")
    page = session.window.page
    moves = await main_world(page, "moves")
    assert len(moves) >= 5
    assert await main_world(page, "overs") == []
    # the small scroll went back where it started
    assert await page.evaluate("() => window.scrollY") == 0
    # another action on the same page: no more movement
    _ = await session.aexecute(type="wait", time_ms=10)
    assert len(await main_world(page, "moves")) == len(moves)
    # a new load: it moves again
    _ = await session.aexecute(type="reload")
    assert len(await main_world(page, "moves")) >= 5
    assert await main_world(page, "overs") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(3))
async def test_the_document_scrolls_a_little_and_back(session: NotteSession, site: str, seed: int) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/calm")
    page = session.window.page
    await page.evaluate("() => window.scrollTo(0, 700)")
    assert await pointer.move_after_load(page, rand=random.Random(seed))
    wheels = await main_world(page, "wheels")
    assert len(wheels) == 2 and float(wheels[0]) > 0 and float(wheels[1]) == -float(wheels[0])
    assert await page.evaluate("() => window.scrollY") == 700


@pytest.mark.asyncio
async def test_movement_after_load_takes_at_least_its_planned_moves(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/busy")
    page = session.window.page
    start = time.monotonic()
    assert await pointer.move_after_load(page, rand=random.Random(5))
    assert time.monotonic() - start >= pointer.AFTER_LOAD_MOVE_S[0]
    assert not await pointer.move_after_load(page)


@pytest.mark.asyncio
@pytest.mark.timing
async def test_movement_after_load_and_the_approach_are_bounded(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/busy")
    page = session.window.page
    start = time.monotonic()
    _ = await pointer.move_after_load(page, rand=random.Random(5))
    assert time.monotonic() - start <= pointer.AFTER_LOAD_MAX_S
    _ = await session.aexecute(type="goto", url=f"{site}/")
    start = time.monotonic()
    assert await pointer.approach(page, page.locator("#buy"), time_left_s=10, rand=random.Random(5)) is not None
    assert time.monotonic() - start <= pointer.APPROACH_S[1] + pointer.APPROACH_MAX_S


@pytest.mark.asyncio
async def test_no_movement_on_a_blank_page(session: NotteSession) -> None:
    page = session.window.page
    assert not await pointer.move_after_load(page)
