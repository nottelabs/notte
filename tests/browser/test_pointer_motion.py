"""The pointer travels to an element before it is clicked, and moves over a page once after it has loaded
(`notte_browser.pointer`)."""

import asyncio
import math
import random
import socket
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import AbstractContextManager, closing
from typing import Any
from unittest.mock import patch

import notte_browser.execution as execution_module
import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser import pointer
from notte_browser.driver import ElementHandle, Locator, Page, evaluate_in_main_world
from notte_browser.session import NotteSession
from notte_core.actions import CheckAction, ClickAction, ScrollDownAction
from notte_core.config import config

# Chrome delivers at most one mousemove per frame, so a slow runner sees fewer
# events than the steps dispatched (the path tests check the step count).
OBSERVED_APPROACH_MOVES = 3

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
    # a product gallery under a pointer cursor over most of the page, a strip of plain text above it
    "/gallery": f"""<html><body style="margin:0; height:3000px">
<p style="height:120px; margin:0">Plain header text</p>
<div class="pointer" style="cursor:pointer; position:absolute; top:120px; left:0; right:0; height:900px"></div>
{RECORD}</body></html>""",
    "/calm": f"""<html><body style="margin:0; height:3000px"><p>Plain text</p>{RECORD}</body></html>""",
    # the first move fills the viewport with buttons, but for a small square around the pointer
    "/reveal": """<html><body style="margin:0; height:3000px"><p>Plain text</p>"""
    + RECORD
    + """<script>
addEventListener('mousemove', e => {
  if (!e.isTrusted || window.revealed) return;
  const [x, y, hole] = [e.clientX, e.clientY, 10];
  window.revealed = [x, y];
  for (const [left, top, width, height] of [
    [0, 0, innerWidth, y - hole], [0, y + hole, innerWidth, innerHeight],
    [0, y - hole, x - hole, 2 * hole], [x + hole, y - hole, innerWidth, 2 * hole],
  ]) {
    const button = document.createElement('button');
    button.style.cssText = `position:fixed; margin:0; padding:0; border:0; left:${left}px; top:${top}px;
      width:${width}px; height:${height}px`;
    document.body.append(button);
  }
}, true);
</script></body></html>""",
    # links in a band at the top of the viewport once the page is scrolled to its bottom, and above it
    "/bottom": f"""<html><body style="margin:0; height:3000px">
<div style="position:absolute; top:2400px; left:0; right:0; height:400px; display:flex; flex-wrap:wrap">
{"".join(f'<a href="#{i}" style="width:20px; height:20px; margin:2px">{i}</a>' for i in range(600))}</div>
{RECORD}</body></html>""",
    # a document that does not scroll, with a scroll container
    "/vanishing": """<html><body style="margin:0"><input type="checkbox" id="gone" style="position:absolute; left:200px; top:200px"></body></html>""",
    "/container": f"""<html><body style="margin:0; height:100vh; overflow:hidden">
<div id="box" style="position:absolute; left:300px; top:100px; width:600px; height:500px; overflow:auto">
<div style="height:3000px">Plain text</div></div>
<button id="go" style="position:absolute; left:1100px; top:700px; width:100px; height:40px">Go</button>
{RECORD}</body></html>""",
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


def pointer_motion_on() -> AbstractContextManager[object]:
    return patch.object(execution_module, "config", config.model_copy(update={"pointer_motion": True}))


@pytest.fixture
def pointer_motion() -> Iterator[None]:
    with pointer_motion_on():
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
    x, y = pointer.middle(visible)
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
    assert len(moves) >= OBSERVED_APPROACH_MOVES
    buy = (600, 400, 120, 40)
    # the approach ends inside the element, where the click lands
    assert inside(moves[-2], buy) and inside(moves[-1], buy) and inside(downs[0][1:3], buy)
    assert not all(inside(move, buy) for move in moves)
    assert all(inside(move, (0, 0, 1280, 800)) for move in moves)


@pytest.mark.asyncio
async def test_after_the_scroll_fallback_the_pointer_travels_from_where_it_was_moved(
    session: NotteSession, site: str
) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/container")
    page = session.window.page
    # the pointer rests outside the scroll container, where a wheel scrolls nothing
    state = pointer.track(page)
    state.moved_after_load = state.loads
    await page.mouse.move(40, 40)
    pointer.moved(page, (40, 40))
    with pointer_motion_on():
        result = await session.aexecute(ScrollDownAction(amount=200), raise_on_failure=True)
        assert result.success
        assert await page.evaluate("() => document.getElementById('box').scrollTop") > 0
        # the scroll fallback moved the pointer over the container
        moves = await main_world(page, "moves")
        fallback = moves[-1]
        assert inside(fallback, (300, 100, 600, 500))
        result = await session.aexecute(ClickAction(selector="#go"), raise_on_failure=True)
        assert result.success
    downs = await main_world(page, "downs")
    approach = (await main_world(page, "moves"))[len(moves) : int(downs[0][3])]
    assert len(approach) >= OBSERVED_APPROACH_MOVES
    # the approach continues from there, not from where the pointer was before the scroll
    assert math.dist(approach[0], fallback) < 60


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
    assert len(moves) >= OBSERVED_APPROACH_MOVES
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
async def test_the_pointer_finds_the_parts_of_a_page_without_controls(
    session: NotteSession, site: str, seed: int
) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/gallery")
    page = session.window.page
    start = time.monotonic()
    assert await pointer.move_after_load(page, rand=random.Random(seed))
    assert time.monotonic() - start >= pointer.AFTER_LOAD_MOVE_S[0]
    moves = await main_world(page, "moves")
    assert len(moves) >= 5
    assert all(float(y) < 120 for _, y in moves)
    assert await main_world(page, "overs") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(3))
async def test_the_document_scrolls_a_little_and_back(session: NotteSession, site: str, seed: int) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/calm")
    page = session.window.page
    await page.evaluate("() => window.scrollTo(0, 700)")
    assert await pointer.move_after_load(page, rand=random.Random(seed))
    wheels = await main_world(page, "wheels")
    assert len(wheels) == 2 and float(wheels[0]) != 0 and float(wheels[1]) == -float(wheels[0])
    assert await page.evaluate("() => window.scrollY") == 700


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(4))
async def test_a_document_at_its_end_is_not_scrolled_back_past_it(session: NotteSession, site: str, seed: int) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/bottom")
    page = session.window.page
    await page.set_viewport_size({"width": 1280, "height": 260})
    # the document at its bottom, links at the top of the viewport and above it
    await page.evaluate("() => window.scrollTo(0, 3000)")
    bottom = await page.evaluate("() => window.scrollY")
    assert await pointer.move_after_load(page, rand=random.Random(seed))
    assert await main_world(page, "overs") == []
    assert await page.evaluate("() => window.scrollY") == bottom


@pytest.mark.asyncio
async def test_a_timeout_after_the_first_wheel_scrolls_the_document_back(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/calm")
    page = session.window.page
    await page.evaluate("() => window.scrollTo(0, 700)")
    wheel = page.mouse.wheel
    wheeled: list[float] = []

    async def wheel_once(delta_x: float, delta_y: float) -> None:
        wheeled.append(await page.evaluate("() => window.scrollY"))
        await wheel(delta_x, delta_y)

    async def sleep(delay: float) -> None:
        if not wheeled:
            await asyncio.sleep(delay)
            return
        # the document scrolled, then the time runs out
        await asyncio.sleep(0.3)
        wheeled.append(await page.evaluate("() => window.scrollY"))
        await asyncio.sleep(60)

    start = time.monotonic()
    with patch.object(page.mouse, "wheel", wheel_once):
        assert not await pointer.move_after_load(page, rand=random.Random(0), sleep=sleep)
    assert time.monotonic() - start <= pointer.AFTER_LOAD_MAX_S + 0.5
    assert len(wheeled) == 2 and wheeled[0] == 700 and wheeled[1] != 700
    assert await page.evaluate("() => window.scrollY") == 700


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(3))
async def test_the_pointer_stops_before_a_control_its_moves_reveal(session: NotteSession, site: str, seed: int) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/reveal")
    page = session.window.page
    assert await pointer.move_after_load(page, rand=random.Random(seed))
    x, y = (float(value) for value in await evaluate_in_main_world(page.main_frame, "revealed"))
    # buttons came under the points planned next: the pointer stays in the square left without them
    assert await main_world(page, "overs") == []
    assert all(
        abs(float(move[0]) - x) < 10 and abs(float(move[1]) - y) < 10 for move in await main_world(page, "moves")
    )
    assert await main_world(page, "wheels") == []


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


@pytest.mark.asyncio
@pytest.mark.usefixtures("pointer_motion")
async def test_a_check_whose_element_is_gone_afterwards_still_succeeds(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/vanishing")
    record = pointer.moved_onto

    async def removed_first(page: Page, element: Locator | ElementHandle) -> None:
        # the page removes the checkbox once it changed, before the pointer is recorded
        _ = await evaluate_in_main_world(page.main_frame, "document.getElementById('gone')?.remove()")
        await record(page, element)

    started = time.monotonic()
    with patch.object(pointer, "moved_onto", removed_first):
        result = await session.aexecute(CheckAction(selector="#gone", value=True, timeout=400), raise_on_failure=False)
    assert result.success, result.message
    # recording where the pointer went does not wait for an element that is gone
    assert time.monotonic() - started < 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("pointer_motion")
async def test_recording_the_pointer_does_not_use_the_actions_deadline(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/vanishing")
    viewport = pointer._viewport  # pyright: ignore[reportPrivateUsage]

    reads: list[float] = []

    async def slow_viewport(page: Page) -> tuple[float, float]:
        # slower than the rest of the action's budget
        reads.append(time.monotonic())
        await asyncio.sleep(0.45)
        return await viewport(page)

    with patch.object(pointer, "_viewport", slow_viewport):
        result = await session.aexecute(CheckAction(selector="#gone", value=True, timeout=400), raise_on_failure=False)
    assert result.success, result.message
    # the record ran (its own bound may skip it on a slow machine), and it did not fail the check
    assert len(reads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(3))
async def test_no_wheel_back_when_it_would_not_scroll_the_document(session: NotteSession, site: str, seed: int) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/calm")
    page = session.window.page
    await page.evaluate("() => window.scrollTo(0, 700)")
    points = pointer._points  # pyright: ignore[reportPrivateUsage]
    wheel = page.mouse.wheel
    wheels: list[float] = []

    async def counted_wheel(delta_x: float, delta_y: float) -> None:
        wheels.append(delta_y)
        await wheel(delta_x, delta_y)

    async def container_after_the_wheel(page: Page, at: list[pointer.Point]) -> Any:
        checked = await points(page, at)
        # once the document moved, a scrollable container is under the pointer
        return {**checked, "wheel": False} if wheels else checked

    with patch.object(page.mouse, "wheel", counted_wheel), patch.object(pointer, "_points", container_after_the_wheel):
        assert await pointer.move_after_load(page, rand=random.Random(seed))
    assert len(wheels) == 1
    assert await page.evaluate("() => window.scrollY") == 700
