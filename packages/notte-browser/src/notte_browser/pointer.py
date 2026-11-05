"""Pointer movement around actions, as a person's pointer moves.

Before a click, the pointer travels along a short curve from where it was to a point inside the element
(`approach`). Once a page has loaded, it moves a little over parts of the page that are not controls and scrolls
the document a little and back (`move_after_load`), once per loaded document. Both are best-effort: an error or
an exhausted time bound skips the movement, never the action. Randomness comes from a `random.Random` that callers
can seed.
"""

import asyncio
import math
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypedDict
from weakref import WeakKeyDictionary

from notte_core.logging import logger

from notte_browser.driver import Error, Locator, Page
from notte_browser.js import script

_POINTER_POINTS = script("pointer_points.js")

Point = tuple[float, float]

# Approach of a click target: steps and duration
APPROACH_STEPS = (12, 25)
APPROACH_S = (0.4, 0.7)
# The approach is skipped when it cannot end this long before the click's own deadline (s)
APPROACH_MAX_S = 1.0
# Movement after a page load: duration of the pointer moves, then a small scroll and back
AFTER_LOAD_MOVE_S = (1.2, 1.8)
AFTER_LOAD_WAYPOINTS = (3, 5)
AFTER_LOAD_SCROLL_PX = (80, 240)
AFTER_LOAD_MAX_S = 3.5
# Points checked across the viewport (columns, rows) for the moves after a load, and moves tried from each point
AFTER_LOAD_GRID = (10, 8)
_SEGMENT_CANDIDATES = 6

rng = random.Random()

Sleep = Callable[[float], Awaitable[None]]


class Box(TypedDict):
    x: float
    y: float
    width: float
    height: float


class _Points(TypedDict):
    width: float
    height: float
    safe: list[bool]
    wheel: bool


@dataclass
class _PointerState:
    # last position the pointer was moved to, None before the first move
    position: Point | None = None
    # documents loaded in the page since it was tracked, and the one the pointer last moved over after its load
    loads: int = 0
    moved_after_load: int = -1


_STATES: WeakKeyDictionary[Page, _PointerState] = WeakKeyDictionary()


def track(page: Page) -> _PointerState:
    """The pointer state of `page`, which counts its document loads from the first call on."""
    state = _STATES.get(page)
    if state is None:
        state = _PointerState()
        _STATES[page] = state

        def on_load(_: Page) -> None:
            state.loads += 1

        page.on("domcontentloaded", on_load)
    return state


def _clamp(point: Point, width: float, height: float) -> Point:
    return min(max(point[0], 0.0), max(width - 1, 0.0)), min(max(point[1], 0.0), max(height - 1, 0.0))


def curve(start: Point, end: Point, steps: int, rand: random.Random, bounds: Point | None = None) -> list[Point]:
    """`steps` points from `start` (excluded) to `end` (the last one, exactly) along a cubic Bezier curve that
    bends to one side, faster in the middle than at both ends, with a pixel or two of jitter. Points other than
    the last one stay within `bounds` (width, height) when given."""
    steps = max(1, steps)
    (x0, y0), (x3, y3) = start, end
    dx, dy = x3 - x0, y3 - y0
    distance = math.hypot(dx, dy)
    # unit normal of the segment, for the bend
    nx, ny = (-dy / distance, dx / distance) if distance > 0 else (0.0, 0.0)
    bend = min(distance * rand.uniform(0.05, 0.25), 120.0) * rand.choice((-1, 1))
    c1 = (x0 + dx * rand.uniform(0.2, 0.4) + nx * bend, y0 + dy * rand.uniform(0.2, 0.4) + ny * bend)
    c2 = (x0 + dx * rand.uniform(0.6, 0.8) + nx * bend * 0.6, y0 + dy * rand.uniform(0.6, 0.8) + ny * bend * 0.6)
    points: list[Point] = []
    for i in range(1, steps + 1):
        s = i / steps
        t = s * s * (3 - 2 * s)  # ease in and out
        u = 1 - t
        x = u**3 * x0 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * x3
        y = u**3 * y0 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * y3
        if i < steps:
            x += rand.gauss(0, 0.8)
            y += rand.gauss(0, 0.8)
            if bounds is not None:
                x, y = _clamp((x, y), *bounds)
        points.append((x, y))
    points[-1] = end
    return points


def point_in(box: Box, rand: random.Random) -> Point:
    """A point in the middle part of `box` (30% to 70% of each side)."""
    return (
        box["x"] + box["width"] * rand.uniform(0.3, 0.7),
        box["y"] + box["height"] * rand.uniform(0.3, 0.7),
    )


def visible_part(box: Box, width: float, height: float) -> Box | None:
    """The part of `box` inside a viewport of `width` x `height`, None when it is out of view."""
    left, top = max(box["x"], 0.0), max(box["y"], 0.0)
    right, bottom = min(box["x"] + box["width"], width), min(box["y"] + box["height"], height)
    if right - left < 1 or bottom - top < 1:
        return None
    return Box(x=left, y=top, width=right - left, height=bottom - top)


async def _move(page: Page, points: list[Point], duration_s: float, sleep: Sleep) -> None:
    """Moves the pointer through `points`, evenly spread over `duration_s`."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    interval = duration_s / max(1, len(points))
    for i, (x, y) in enumerate(points, start=1):
        await page.mouse.move(x, y)
        delay = start + i * interval - loop.time()
        if delay > 0:
            await sleep(delay)


async def _viewport(page: Page) -> Point:
    size = page.viewport_size
    if size is not None:
        return float(size["width"]), float(size["height"])
    points: _Points = await page.evaluate(_POINTER_POINTS, [])
    return float(points["width"]), float(points["height"])


async def approach(
    page: Page, locator: Locator, *, time_left_s: float, rand: random.Random | None = None, sleep: Sleep = asyncio.sleep
) -> Point | None:
    """Moves the pointer to a point inside the element of `locator`, scrolled into view first, along a curve
    from where it was. Returns that point, or None when the element is not visible or the approach could not end
    within `time_left_s`; the click then goes ahead as it would have without it."""
    rand = rand or rng
    duration = rand.uniform(*APPROACH_S)
    if time_left_s < duration + APPROACH_MAX_S:
        return None
    state = track(page)
    scope = asyncio.timeout(APPROACH_MAX_S + duration)
    try:
        async with scope:
            if not await locator.is_visible():
                return None
            await locator.scroll_into_view_if_needed(timeout=APPROACH_MAX_S * 1000)
            box = await locator.bounding_box(timeout=APPROACH_MAX_S * 1000)
            if box is None:
                return None
            width, height = await _viewport(page)
            visible = visible_part(Box(x=box["x"], y=box["y"], width=box["width"], height=box["height"]), width, height)
            if visible is None:
                return None
            target = point_in(visible, rand)
            start = state.position or (rand.uniform(0.2, 0.8) * width, rand.uniform(0.2, 0.8) * height)
            path = curve(start, target, rand.randint(*APPROACH_STEPS), rand, (width, height))
            if state.position is None:
                path.insert(0, start)
            await _move(page, path, duration, sleep)
            state.position = target
            return target
    except TimeoutError:
        if not scope.expired():
            raise
    except Error as error:
        logger.debug(f"Pointer approach skipped: {type(error).__name__}")
    return None


def _grid(width: float, height: float, rand: random.Random) -> list[Point]:
    """One point at random in each cell of a grid over the viewport, away from its edges."""
    columns, rows = AFTER_LOAD_GRID
    cell_w, cell_h = width * 0.94 / columns, height * 0.94 / rows
    return [
        (width * 0.03 + (c + rand.uniform(0.2, 0.8)) * cell_w, height * 0.03 + (r + rand.uniform(0.2, 0.8)) * cell_h)
        for r in range(rows)
        for c in range(columns)
    ]


def _segments(
    current: Point,
    targets: list[Point],
    width: float,
    height: float,
    rand: random.Random,
    *,
    nearby: int = 2,
    reach: tuple[float, float] = (15, 60),
) -> list[list[Point]]:
    """Candidate moves from `current`: curves to a few of `targets`, then `nearby` short moves around it."""
    others = [target for target in targets if target != current]
    segments = [
        curve(current, target, rand.randint(6, 12), rand, (width, height))
        for target in rand.sample(others, min(len(others), _SEGMENT_CANDIDATES))
    ]
    for _ in range(nearby):
        angle = rand.uniform(0, 2 * math.pi)
        distance = rand.uniform(*reach)
        close = _clamp(
            (current[0] + math.cos(angle) * distance, current[1] + math.sin(angle) * distance), width, height
        )
        segments.append(curve(current, close, rand.randint(3, 6), rand, (width, height)))
    return segments


async def _points(page: Page, points: list[Point]) -> _Points:
    return await page.evaluate(_POINTER_POINTS, [list(point) for point in points])


async def move_after_load(page: Page, *, rand: random.Random | None = None, sleep: Sleep = asyncio.sleep) -> bool:
    """Once per document loaded in `page`: moves the pointer over points of the viewport that are not on a
    control (a link, a button, a field, a frame, an element with a pointer cursor, ...), then scrolls the document a
    little and back when the pointer rests on it. Every point the pointer goes through is checked first: it moves
    from one checked point to the next across parts of the page without controls, and only around where it is when
    there are none. Bounded by `AFTER_LOAD_MAX_S`. Returns whether it moved."""
    rand = rand or rng
    state = track(page)
    if state.moved_after_load == state.loads or page.is_closed():
        return False
    if not page.url.startswith(("http://", "https://")):
        return False
    state.moved_after_load = state.loads
    scope = asyncio.timeout(AFTER_LOAD_MAX_S)
    try:
        async with scope:
            width, height = await _viewport(page)
            if width < 50 or height < 50:
                return False
            grid = _grid(width, height, rand)
            start = state.position or (rand.uniform(0.3, 0.7) * width, rand.uniform(0.3, 0.7) * height)
            verdicts = await _points(page, [start, *grid])
            targets = [point for point, safe in zip(grid, verdicts["safe"][1:]) if safe]
            if not verdicts["safe"][0]:
                if not targets:
                    return False
                # the pointer comes in over a part of the page without controls
                start = rand.choice(targets)
            path = [start]
            for _ in range(rand.randint(*AFTER_LOAD_WAYPOINTS)):
                safe = None
                # then shorter moves only, where controls leave little room
                for attempt in range(3):
                    segments = (
                        _segments(path[-1], targets, width, height, rand)
                        if attempt == 0
                        else _segments(path[-1], [], width, height, rand, nearby=6, reach=(6, 30 / attempt))
                    )
                    checked = await _points(page, [point for segment in segments for point in segment])
                    offset = 0
                    for segment in segments:
                        if all(checked["safe"][offset : offset + len(segment)]):
                            safe = segment
                            break
                        offset += len(segment)
                    if safe is not None:
                        break
                if safe is None:
                    break
                path.extend(safe)
            if len(path) < 2:
                return False
            await _move(page, path, rand.uniform(*AFTER_LOAD_MOVE_S), sleep)
            state.position = path[-1]
            # The scroll moves the page under the pointer: what comes under it is checked too, the part of the page
            # below it (above it, near the bottom of the viewport) by the length of the scroll.
            x, y = path[-1]
            sign = 1 if height - 1 - y >= AFTER_LOAD_SCROLL_PX[0] else -1
            delta = min(rand.randint(*AFTER_LOAD_SCROLL_PX), int(height - 1 - y if sign > 0 else y))
            column = [(x, y + sign * dy) for dy in range(0, delta, 10)] + [(x, y + sign * delta)]
            checked = await _points(page, column) if delta >= AFTER_LOAD_SCROLL_PX[0] else None
            if checked is not None and checked["wheel"] and all(checked["safe"]):
                delta *= sign
                before: float = await page.evaluate("() => window.scrollY")
                await page.mouse.wheel(0, delta)
                await sleep(rand.uniform(0.25, 0.45))
                await page.mouse.wheel(0, -delta)
                await sleep(rand.uniform(0.2, 0.35))
                # a page at its bottom scrolls down less than back up
                await page.evaluate(
                    "(y) => { if (window.scrollY !== y) window.scrollTo({ top: y, behavior: 'instant' }) }", before
                )
            return True
    except TimeoutError:
        if not scope.expired():
            raise
    except Error as error:
        logger.debug(f"Pointer movement after load skipped: {type(error).__name__}")
    return False
