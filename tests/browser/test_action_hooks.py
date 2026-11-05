"""Hooks installed around the input of `execute` (`notte_browser.action_hooks`)."""

import asyncio
import socket
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import closing

import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser import action_hooks
from notte_browser.action_hooks import ActionHooks, Point, install_action_hooks, use_action_hooks
from notte_browser.driver import Locator, Page, evaluate_in_main_world
from notte_browser.session import NotteSession
from notte_core.actions import CheckAction, ClickAction

RECORD = """<script>
window.moves = 0; window.downs = [];
addEventListener('mousemove', e => { if (e.isTrusted) moves += 1 }, true);
addEventListener('mousedown', e => { if (e.isTrusted) downs.push(e.target.id) }, true);
</script>"""

PAGES = {
    "/": f"""<html><body>
<button id="stay" style="position:absolute; left:400px; top:300px; width:120px; height:40px">Stay</button>
<a id="next" href="/next" style="position:absolute; left:100px; top:100px">Next</a>
<a id="tab" href="/next" target="_blank" style="position:absolute; left:100px; top:200px">Tab</a>
<input type="checkbox" id="box" style="position:absolute; left:100px; top:400px">{RECORD}</body></html>""",
    "/next": f"<html><body><p>Next page</p>{RECORD}</body></html>",
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


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=800) as session:
        yield session


class Recorder(ActionHooks):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.click_budgets: list[float] = []
        self.moves: list[Point | None] = []

    async def before_click(self, page: Page, locator: Locator, time_left_s: float) -> None:
        self.calls.append(("before_click", await locator.get_attribute("id") or ""))
        self.click_budgets.append(time_left_s)

    async def after_navigation(self, page: Page, time_left_s: float) -> None:
        self.calls.append(("after_navigation", page.url.rsplit("/", 1)[-1]))

    def pointer_moved(self, page: Page, point: Point | None) -> None:
        self.moves.append(point)


@pytest.fixture
def recorder() -> Iterator[Recorder]:
    hooks = Recorder()
    with use_action_hooks(hooks):
        yield hooks


def test_no_hooks_by_default() -> None:
    assert action_hooks.active_action_hooks() is None


def test_scoped_hooks_take_precedence_over_the_process_hooks() -> None:
    process, scoped = ActionHooks(), ActionHooks()
    assert install_action_hooks(process) is None
    try:
        assert action_hooks.active_action_hooks() is process
        with use_action_hooks(scoped):
            assert action_hooks.active_action_hooks() is scoped
        assert action_hooks.active_action_hooks() is process
    finally:
        assert install_action_hooks(None) is process
    assert action_hooks.active_action_hooks() is None


@pytest.mark.asyncio
async def test_a_click_calls_before_click_with_its_element_and_budget(
    session: NotteSession, site: str, recorder: Recorder
) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    recorder.calls.clear()
    result = await session.aexecute(ClickAction(selector="#stay", timeout=5000), raise_on_failure=True)
    assert result.success
    # the click navigated nowhere: no after_navigation
    assert recorder.calls == [("before_click", "stay")]
    # the click keeps a fifth of its timeout and a second for itself
    assert 0 < recorder.click_budgets[0] <= 5.0 - 1.0 - 1.0
    assert await evaluate_in_main_world(session.window.page.main_frame, "downs") == ["stay"]


@pytest.mark.asyncio
async def test_navigations_call_after_navigation(session: NotteSession, site: str, recorder: Recorder) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    assert recorder.calls == [("after_navigation", "")]
    _ = await session.aexecute(ClickAction(selector="#next"), raise_on_failure=True)
    assert recorder.calls[1:] == [("before_click", "next"), ("after_navigation", "next")]
    recorder.calls.clear()
    _ = await session.aexecute(type="go_back")
    _ = await session.aexecute(type="reload")
    assert recorder.calls == [("after_navigation", ""), ("after_navigation", "")]
    recorder.calls.clear()
    _ = await session.aexecute(type="wait", time_ms=10)
    assert recorder.calls == []


@pytest.mark.asyncio
async def test_a_click_that_opens_a_tab_calls_after_navigation_with_it(
    session: NotteSession, site: str, recorder: Recorder
) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    recorder.calls.clear()
    _ = await session.aexecute(ClickAction(selector="#tab"), raise_on_failure=True)
    assert session.window.page.url == f"{site}/next"
    assert recorder.calls == [("before_click", "tab"), ("after_navigation", "next")]


@pytest.mark.asyncio
async def test_a_driver_move_is_reported(session: NotteSession, site: str, recorder: Recorder) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    result = await session.aexecute(CheckAction(selector="#box", value=True), raise_on_failure=True)
    assert result.success
    assert recorder.moves == [None]


class Failing(ActionHooks):
    async def before_click(self, page: Page, locator: Locator, time_left_s: float) -> None:
        raise RuntimeError("hook failed")

    async def after_navigation(self, page: Page, time_left_s: float) -> None:
        raise RuntimeError("hook failed")

    def pointer_moved(self, page: Page, point: Point | None) -> None:
        raise RuntimeError("hook failed")


@pytest.mark.asyncio
async def test_a_failing_hook_does_not_fail_the_action(session: NotteSession, site: str) -> None:
    with use_action_hooks(Failing()):
        assert (await session.aexecute(type="goto", url=f"{site}/")).success
        assert (await session.aexecute(ClickAction(selector="#stay"), raise_on_failure=True)).success
        assert (await session.aexecute(CheckAction(selector="#box", value=True), raise_on_failure=True)).success
    assert await evaluate_in_main_world(session.window.page.main_frame, "downs") == ["stay", "box"]


class Stalled(ActionHooks):
    def __init__(self) -> None:
        self.started: list[str] = []

    async def before_click(self, page: Page, locator: Locator, time_left_s: float) -> None:
        self.started.append("before_click")
        await asyncio.sleep(60)

    async def after_navigation(self, page: Page, time_left_s: float) -> None:
        self.started.append("after_navigation")
        await asyncio.sleep(60)


@pytest.mark.asyncio
@pytest.mark.timing
async def test_a_stalled_hook_is_stopped_within_its_budget(session: NotteSession, site: str) -> None:
    hooks = Stalled()
    with use_action_hooks(hooks):
        start = time.monotonic()
        assert (await session.aexecute(type="goto", url=f"{site}/")).success
        # the goto's own wait aside, the hook had its second
        assert time.monotonic() - start < 30
        start = time.monotonic()
        result = await session.aexecute(ClickAction(selector="#stay", timeout=4000), raise_on_failure=True)
        assert result.success
        # the click still lands within its own timeout
        assert time.monotonic() - start < 4.5
    assert hooks.started == ["after_navigation", "before_click"]
    assert await evaluate_in_main_world(session.window.page.main_frame, "downs") == ["stay"]


@pytest.mark.asyncio
@pytest.mark.timing
async def test_after_navigation_is_bounded(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    with use_action_hooks(Stalled()):
        start = time.monotonic()
        assert (await session.aexecute(type="reload")).success
        elapsed = time.monotonic() - start
    unhooked_start = time.monotonic()
    assert (await session.aexecute(type="reload")).success
    unhooked = time.monotonic() - unhooked_start
    assert elapsed - unhooked < action_hooks.AFTER_NAVIGATION_TIMEOUT_S + 1.0
    assert elapsed >= action_hooks.AFTER_NAVIGATION_TIMEOUT_S


@pytest.mark.asyncio
async def test_without_hooks_a_click_moves_the_pointer_once(session: NotteSession, site: str) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    assert (await session.aexecute(ClickAction(selector="#stay"), raise_on_failure=True)).success
    assert await evaluate_in_main_world(session.window.page.main_frame, "moves") <= 1


@pytest.mark.asyncio
async def test_a_check_that_changes_nothing_reports_no_move(
    session: NotteSession, site: str, recorder: Recorder
) -> None:
    _ = await session.aexecute(type="goto", url=f"{site}/")
    _ = await session.aexecute(CheckAction(selector="#box", value=True), raise_on_failure=True)
    recorder.moves.clear()
    # already checked: the box is not clicked
    result = await session.aexecute(CheckAction(selector="#box", value=True), raise_on_failure=True)
    assert result.success
    assert recorder.moves == []
