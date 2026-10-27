"""`execute()` waits until the page has reacted to an action (`notte_browser.settle`), not for fixed delays."""

import asyncio
import io
import socket
import time
from collections.abc import AsyncIterator
from contextlib import ExitStack, closing, suppress
from typing import Literal
from unittest.mock import AsyncMock, patch

import notte_browser.execution as execution_module
import notte_browser.settle as settle_module
import notte_browser.window as window_module
import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.driver import Error, JSHandle, Locator, Page, evaluate_in_main_world
from notte_browser.driver import TimeoutError as PlaywrightTimeoutError
from notte_browser.session import NotteSession
from notte_browser.settle import CAP_MS, LONG_GRACE_MS, QUIET_MS, SETTLE_MS, PageSettle
from notte_browser.window import BrowserWindow
from notte_core.actions import (
    ClickAction,
    GoBackAction,
    GoForwardAction,
    InteractionAction,
    PressKeyAction,
    ScrollDownAction,
)
from notte_core.config import config
from notte_core.errors import NotteBaseError
from notte_core.snapshot import BrowserSnapshot
from patchright.async_api import Route
from PIL import Image

HOME = """<html><body>
<a id="next" href="/next">Next page</a>
<a id="tab" href="/second" target="_blank">Open in a new tab</a>
<button id="later-tab" onclick="setTimeout(() => window.open('/second'), 100)">Open a tab later</button>
<button id="slow-tab" onclick="window.open('/slow-second')">Open a slow tab</button>
<button id="late-timer-tab" onclick="setTimeout(() => window.open('/second'), 1200)">Open a tab much later</button>
<button id="late-fetching-tab" onclick="setTimeout(() => window.open('/fetching-tab'), 1200)">Open a fetching tab later</button>
<button id="timer-nav" onclick="setTimeout(() => { location.href = '/next' }, 300)">Go later</button>
<button id="spa" onclick="setTimeout(() => { history.pushState({}, '', '/spa');
  setTimeout(() => document.body.insertAdjacentHTML('beforeend', '<h2>Spa page</h2>'), 100) }, 300)">Spa</button>
<button id="fetch" onclick="fetch('/data?delay=0.7').then(() =>
  document.body.insertAdjacentHTML('beforeend', '<p>Fetched result</p>'))">Load</button>
<button id="late" onclick="setTimeout(() =>
  document.body.insertAdjacentHTML('beforeend', '<p>Late result</p>'), 400)">Late</button>
<button id="nothing">Nothing</button>
<button id="hang" onclick="fetch('/hang')">Hang</button>
<a id="hang-page" href="/hanging">Hanging page</a>
<form action="/results"><input id="q" name="q" value="lamp"></form>
<a id="late-load" href="/late-load">Late load</a>
<a id="late-load-timer" href="/late-load-timer">Late load, then a timer</a>
<button id="widget" onclick="document.body.append(document.createElement('x-widget'))">Widget</button>
<button id="nested" onclick="document.body.append(document.createElement('x-outer'))">Nested widget</button>
<button id="open-helper" onclick="window.helper = window.open('/next')">Open a helper tab</button>
<button id="swap-tab" onclick="window.helper.close(); window.open('/second')">Swap tabs</button>
<script>customElements.define('x-widget', class extends HTMLElement {
  connectedCallback() {
    const root = this.attachShadow({ mode: 'open' });
    setTimeout(() => { root.innerHTML = '<p>Loading</p>' }, 150);
    setTimeout(() => { root.innerHTML = '<p>Widget content</p>' }, 300);
  }
});
// renders an inner widget in its shadow root right away: the inner one renders in steps in its own
customElements.define('x-outer', class extends HTMLElement {
  connectedCallback() { this.attachShadow({ mode: 'open' }).innerHTML = '<x-inner></x-inner>'; }
});
customElements.define('x-inner', class extends HTMLElement {
  connectedCallback() {
    const root = this.attachShadow({ mode: 'open' });
    setTimeout(() => { root.innerHTML = '<p>Loading</p>' }, 150);
    setTimeout(() => { root.innerHTML = '<p>Inner content</p>' }, 300);
  }
});</script>
<button id="frame" onclick="document.getElementById('inner').src = '/inner'">Frame</button>
<iframe id="inner" src="about:blank"></iframe>
<a id="fetching-tab" href="/fetching-tab" target="_blank">Open a tab that fetches</a>
<button id="replace-self" onclick="window.open('/fetching-tab'); window.close()">Replace this tab</button>
<button id="close-self" onclick="setTimeout(() => window.close(), 100)">Close this tab</button>
<a id="download" href="/download" target="_blank">Download</a>
<button id="pages" onclick="fetch('/data?delay=0.1').then(() => fetch('/data?delay=0.6')).then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>Both pages fetched</p>'))">Fetch pages</button>
<button id="retry" onclick="fetch('/data?delay=0.4').then(() => fetch('/data?delay=0.4')).then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>Retried result</p>'))">Retry</button>
<a id="product" href="/product">Product</a>
<a id="api-product" href="/api-product">Product from an API</a>
<button id="route" onclick="const chunk = document.createElement('script'); chunk.src = '/chunk.js';
  document.head.append(chunk)">Contact</button>
</body></html>"""
PAGES = {
    "/": HOME,
    # rendered once its own data arrives, after its load event; red, to tell it apart in a screenshot
    "/next": """<html><body style="background: rgb(255, 0, 0)"><h1>Next</h1><script>
window.addEventListener('load', () => fetch('/data?delay=0.3').then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>Rendered after load</p>')));
</script></body></html>""",
    "/second": "<html><body><h1>Second tab</h1></body></html>",
    # answers after the 500 ms a click with no visible effect is waited for
    "/slow-second": "<html><body><h1>Second tab</h1></body></html>",
    # parsed past a script that takes 300 ms, then keeps a request in flight (analytics, polling)
    "/results": """<html><body><h1>Results</h1><script src="/slow.js"></script><p>First result</p>
<script>fetch('/hang')</script></body></html>""",
    "/hanging": "<html><body><h1>Hanging</h1><script>fetch('/hang')</script></body></html>",
    # its button is covered for 700 ms
    "/covered": """<html><body><button id="covered" onclick="setTimeout(() =>
  document.body.insertAdjacentHTML('beforeend', '<p>Covered result</p>'), 300)">Covered</button>
<div id="cover" style="position: fixed; inset: 0; background: white"></div>
<script>setTimeout(() => document.getElementById('cover').remove(), 700)</script></body></html>""",
    # loads after a slow image, then fetches what it renders
    "/late-load": """<html><body><h1>Late load</h1><img src="/slow-image"><script>
window.addEventListener('load', () => fetch('/data?delay=0.3').then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>Rendered after a late load</p>')));
</script></body></html>""",
    # a hash handler redirects here: loading outlasts even the same-document URL-change expectation
    "/redirect-load": """<html><body><h1>Redirect destination</h1><img src="/slow-image?delay=2"><script>
window.addEventListener('load', () => fetch('/data?delay=0.3').then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>Rendered after redirect load</p>')));
</script></body></html>""",
    # loads after a slow image, then fetches what it renders on a short timer
    "/late-load-timer": """<html><body><h1>Late load</h1><img src="/slow-image"><script>
window.addEventListener('load', () => setTimeout(() => fetch('/data?delay=0.3').then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>Rendered after a late load</p>')), 50));
</script></body></html>""",
    # renders in two steps after it loaded in a frame
    "/inner": """<html><body><script>
window.addEventListener('load', () => {
    setTimeout(() => { document.body.innerHTML = '<p>Loading</p>' }, 150);
    setTimeout(() => { document.body.innerHTML = '<p>Still loading</p>' }, 300);
    setTimeout(() => { document.body.innerHTML = '<p>Frame content</p>' }, 450);
});
</script></body></html>""",
    # loads at once, then fetches what it renders on a timer (a product page's data)
    "/product": """<html><body><h1>Shop</h1><script>
window.addEventListener('load', () => setTimeout(() => fetch('/data?delay=0.3').then(() =>
    document.body.insertAdjacentHTML('beforeend', '<button>Add to cart</button>')), 250));
</script></body></html>""",
    # loads at once, fetches its settings, then its product from an API on another origin: a JSON POST, sent after
    # a CORS preflight, which the browser reports only once the preflight has answered
    "/api-product": """<html><body><h1>Shop</h1><script>
fetch('/data?delay=0.8').then(() => fetch(`http://localhost:${location.port}/api`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }
)).then(() => document.body.insertAdjacentHTML('beforeend', '<button>Add to cart</button>'));
</script></body></html>""",
    # answers late, then never loads (an image that never arrives)
    "/slow-stalled": """<html><body><h1>Stalled</h1><img src="/hang"></body></html>""",
    # commits after the same-document settle cap, then fetches data within the navigation budget
    "/slow-commit": """<html><body><h1>Slow response</h1><script>
window.addEventListener('load', () => fetch('/data?delay=0.3').then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>Slow page content</p>')));
</script></body></html>""",
    # loads at once, then fetches its content from a slow API on a timer (a single-page app)
    "/app": """<html><body><h1>App</h1><script>
window.addEventListener('load', () => setTimeout(() => fetch('/data?delay=0.9').then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>App content</p>')), 300));
</script></body></html>""",
    # fetches its content as soon as it is parsed
    "/fetching-tab": """<html><body><h1>Fetching tab</h1><script>fetch('/data?delay=0.6').then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>Fetched in the tab</p>'))</script></body></html>""",
    # pages that change on their own, whatever the action does
    "/clock": """<html><body><button id="nothing">Nothing</button><span id="clock"></span>
<div id="slide" class="slide"></div><script>setInterval(() => {
    document.getElementById('clock').textContent = Date.now();
    document.getElementById('slide').classList.toggle('active');
}, 100)</script></body></html>""",
    "/polling": """<html><body><button id="nothing">Nothing</button>
<script>setInterval(() => fetch('/data?delay=0.25'), 300)</script></body></html>""",
    # the frame (an ad) is on another origin, and fetches when the page posts to it
    "/ad-page": """<html><body><button id="nothing" onclick="frames[0].postMessage('click', '*')">Nothing</button>
<iframe src="OTHER_ORIGIN/ad"></iframe></body></html>""",
    "/ad": """<html><body>Ad<script>window.addEventListener('message', () => fetch('/data?delay=2'))</script>
</body></html>""",
    # renders its results from data it fetches once it is parsed
    "/search": """<html><body><form action="/search-results"><input id="query" name="q" value="lamp">
<button id="submit">Search</button></form></body></html>""",
    "/search-results": """<html><body><h1>Results</h1><div id="results">Loading</div><script>
fetch('/data?delay=0.5').then(() => { document.getElementById('results').textContent = 'Lamp results' })
</script></body></html>""",
    # loads more items once scrolled to the bottom
    "/feed": """<html><body><div style="height: 3000px">Feed</div><div id="end"></div><script>
new IntersectionObserver(([entry]) => { if (entry.isIntersecting) fetch('/data?delay=0.4').then(() =>
    document.body.insertAdjacentHTML('beforeend', '<p>More items</p>')) }).observe(document.getElementById('end'))
</script></body></html>""",
}
# each page takes this long to answer, a slow one longer
PAGE_DELAY_S = 0.2
SLOW_PAGE_DELAY_S = 0.8


@pytest_asyncio.fixture(loop_scope="function")
async def site() -> AsyncIterator[str]:
    release = asyncio.Event()

    async def page(request: web.Request) -> web.Response:
        delay = SLOW_PAGE_DELAY_S if request.path.startswith("/slow") else PAGE_DELAY_S
        if request.path == "/slow-commit":
            delay = CAP_MS / 1000 + 0.2
        await asyncio.sleep(delay)
        # the same server on another host name is another origin
        other_origin = f"http://localhost:{port}"
        return web.Response(text=PAGES[request.path].replace("OTHER_ORIGIN", other_origin), content_type="text/html")

    async def data(request: web.Request) -> web.Response:
        await asyncio.sleep(float(request.query["delay"]))
        return web.json_response({})

    async def slow_script(_request: web.Request) -> web.Response:
        await asyncio.sleep(0.3)
        return web.Response(text="", content_type="text/javascript")

    cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    async def api_preflight(_request: web.Request) -> web.Response:
        await asyncio.sleep(0.4)
        return web.Response(headers=cors)

    async def api(_request: web.Request) -> web.Response:
        return web.json_response({}, headers=cors)

    async def chunk(_request: web.Request) -> web.Response:
        # a route's code, loaded on demand: it changes the URL and renders once it has arrived
        await asyncio.sleep(0.8)
        script = """history.pushState({}, '', '/contact');
document.body.insertAdjacentHTML('beforeend', '<h2>Contact page</h2>');"""
        return web.Response(text=script, content_type="text/javascript")

    async def slow_image(request: web.Request) -> web.Response:
        await asyncio.sleep(float(request.query.get("delay", "1")))
        return web.Response(status=404)

    async def hang(_request: web.Request) -> web.Response:
        await release.wait()
        return web.json_response({})

    async def download(_request: web.Request) -> web.Response:
        return web.Response(body=b"downloaded", headers={"Content-Disposition": "attachment; filename=result.txt"})

    app = web.Application()
    for path in PAGES:
        app.router.add_get(path, page)
    app.router.add_get("/data", data)
    app.router.add_get("/slow.js", slow_script)
    app.router.add_get("/chunk.js", chunk)
    app.router.add_route("OPTIONS", "/api", api_preflight)
    app.router.add_post("/api", api)
    app.router.add_get("/slow-image", slow_image)
    app.router.add_get("/hang", hang)
    app.router.add_get("/download", download)
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        port = server_socket.getsockname()[1]
        await web.SockSite(runner, server_socket).start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            release.set()
            await runner.cleanup()


@pytest_asyncio.fixture(loop_scope="function")
async def session(site: str) -> AsyncIterator[NotteSession]:
    async with NotteSession(headless=True) as session:
        _ = await session.aexecute(type="goto", url=f"{site}/", wait_until="load")
        yield session


async def text(session: NotteSession) -> str:
    return await session.window.page.inner_text("body")


async def click(session: NotteSession, element: str) -> float:
    """Clicks `#element`, returns how long `execute()` took (s)."""
    start = time.monotonic()
    result = await session.aexecute(ClickAction(selector=f"#{element}"), raise_on_failure=True)
    assert result.success
    return time.monotonic() - start


@pytest.mark.asyncio
@pytest.mark.parametrize("opener", ["tab", "later-tab", "slow-tab"])
async def test_a_click_that_opens_a_tab_switches_to_it_once_it_has_loaded(
    session: NotteSession, site: str, opener: str
) -> None:
    _ = await click(session, opener)
    assert len(session.window.page.context.pages) == 2
    assert session.window.page.url == f"{site}/{'slow-second' if opener == 'slow-tab' else 'second'}"
    assert await session.window.page.evaluate("document.readyState") == "complete"
    assert "Second tab" in await text(session)


@pytest.mark.asyncio
async def test_a_tab_opened_after_the_settle_is_switched_to_by_the_next_observation(
    session: NotteSession, site: str
) -> None:
    async with session.window.page.context.expect_page() as opened:
        _ = await click(session, "late-timer-tab")
        # the click had no visible effect: its settle ended before the tab opened
        assert len(session.window.page.context.pages) == 1
    _ = await opened.value
    observation = await session.aobserve()
    assert observation.metadata.url == f"{site}/second"
    assert session.window.page.url == f"{site}/second"
    assert "Second tab" in await text(session)


@pytest.mark.asyncio
async def test_an_empty_observation_keeps_watching_for_a_late_tab(session: NotteSession, site: str) -> None:
    # Release the deferred open explicitly so the first observation always precedes it.
    await session.window.page.evaluate(
        "document.getElementById('late-timer-tab').onclick = () => { window.openLater = () => window.open('/second'); }"
    )
    _ = await click(session, "late-timer-tab")
    first = await session.aobserve()
    assert first.metadata.url == f"{site}/"
    async with session.window.page.context.expect_page() as opened:
        await session.window.page.evaluate("window.openLater()")
    _ = await opened.value
    observation = await session.aobserve()
    assert observation.metadata.url == f"{site}/second"
    assert "Second tab" in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("closing_count", [1, 2])
async def test_observation_tries_earlier_tabs_when_newest_tabs_close(
    session: NotteSession, site: str, closing_count: int
) -> None:
    window = session.window
    context = window.page.context
    await window.watch_new_tabs(True)
    survivor = await context.new_page()
    _ = await survivor.goto(f"{site}/fetching-tab")
    closing_tabs: list[Page] = []
    for _ in range(closing_count):
        tab = await context.new_page()
        _ = await tab.goto(f"{site}/second")
        closing_tabs.append(tab)
    settles = list(window._new_tabs.values())
    survivor_settle = window._new_tabs[survivor]
    with ExitStack() as stack:
        closed = [stack.enter_context(patch.object(settle, "close", wraps=settle.close)) for settle in settles]
        wait = stack.enter_context(patch.object(survivor_settle, "wait", wraps=survivor_settle.wait))
        for tab in closing_tabs:

            async def close_on_front(tab: Page = tab) -> None:
                await tab.close()
                raise Error("Page closed during bring_to_front")

            _ = stack.enter_context(patch.object(tab, "bring_to_front", side_effect=close_on_front))
        observation = await session.aobserve()
        assert observation.metadata.url == f"{site}/fetching-tab"
        assert "Fetched in the tab" in await text(session)
        wait.assert_awaited_once_with(document="requests")
        for close in closed:
            close.assert_awaited_once()
    assert window._tabs_context is None and not window._new_tabs


@pytest.mark.asyncio
async def test_observation_keeps_watching_when_every_candidate_closes(session: NotteSession, site: str) -> None:
    window = session.window
    context = window.page.context
    await window.watch_new_tabs(True)
    tab = await context.new_page()
    _ = await tab.goto(f"{site}/second")

    async def close_on_front() -> None:
        await tab.close()
        raise Error("Page closed during bring_to_front")

    with patch.object(tab, "bring_to_front", side_effect=close_on_front):
        assert (await session.aobserve()).metadata.url == f"{site}/"
    assert window._tabs_context is context
    assert not window._new_tabs
    later = await context.new_page()
    _ = await later.goto(f"{site}/second")
    assert (await session.aobserve()).metadata.url == f"{site}/second"


@pytest.mark.asyncio
async def test_a_late_tab_is_not_switched_to_after_another_action(session: NotteSession, site: str) -> None:
    async with session.window.page.context.expect_page() as opened:
        _ = await click(session, "late-timer-tab")
    _ = await opened.value
    # acted on the first tab since: the late tab is the earlier action's
    _ = await click(session, "nothing")
    observation = await session.aobserve()
    assert observation.metadata.url == f"{site}/"
    assert len(session.window.page.context.pages) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("close_opener", [False, True])
async def test_a_late_tab_s_requests_are_waited_for_from_when_it_appears(
    session: NotteSession, site: str, close_opener: bool
) -> None:
    opener = session.window.page
    async with session.window.page.context.expect_page() as opened:
        _ = await click(session, "late-fetching-tab")
    tab = await opened.value
    # its fetch has started when the observation begins
    await tab.wait_for_load_state("domcontentloaded")
    if close_opener:
        await opener.close()
        assert session.window.page is tab
    observation = await session.aobserve()
    assert observation.metadata.url == f"{site}/fetching-tab"
    assert "Fetched in the tab" in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_opener", [False, True])
async def test_observation_waits_for_a_request_sent_before_the_tab_tracker_exists(
    session: NotteSession, site: str, close_opener: bool
) -> None:
    """Context requests can arrive before the tab's page event installs its tracker."""
    window = session.window
    opener = window.page
    context = opener.context
    fetching = asyncio.Event()
    release = asyncio.Event()

    async def serve(route: Route) -> None:
        if route.request.url.endswith("/early-data"):
            fetching.set()
            await release.wait()
            await route.fulfill(body="{}", content_type="application/json")
        else:
            await route.fulfill(
                body="""<h1>Fetching tab</h1><script>fetch('/early-data').then(() =>
                    document.body.insertAdjacentHTML('beforeend', '<p>Fetched in the tab</p>'))</script>""",
                content_type="text/html",
            )

    await context.route(f"{site}/early-*", serve)
    await window.watch_new_tabs(False)
    record = window._new_tab
    pending: list[Page] = []

    # Deliver the page callback only after its real request starts, reproducing the event-order race.
    def defer(page: Page) -> None:
        pending.append(page)

    with patch.object(window, "_new_tab", new=defer):
        await window.watch_new_tabs(True)
        try:
            tab = await context.new_page()
            await tab.goto(f"{site}/early-page")
            await fetching.wait()
            assert pending == [tab]
            record(tab)
            if close_opener:
                await opener.close()
                assert window.page is tab
            observation = asyncio.create_task(session.aobserve())
            try:
                done, _ = await asyncio.wait({observation}, timeout=SETTLE_MS / 1000)
                assert not done, "Observation finished while the tab's content request was still blocked"
                release.set()
                assert (await observation).metadata.url == f"{site}/early-page"
                assert "Fetched in the tab" in await text(session)
            finally:
                release.set()
                _ = await asyncio.gather(observation, return_exceptions=True)
        finally:
            release.set()
            await window.watch_new_tabs(False)


@pytest.mark.asyncio
async def test_closing_a_borrowed_window_stops_tracking_new_tabs(session: NotteSession) -> None:
    page = session.window.page
    window = window_module.BrowserWindow(page, session.window.options)
    await window.watch_new_tabs(True)
    tab = await page.context.new_page()
    settle = window._new_tabs[tab]
    with patch.object(settle, "close", wraps=settle.close) as close:
        await window.close()
        close.assert_awaited_once()
    assert not page.is_closed()
    assert window._tabs_context is None
    assert not window._new_tabs
    _ = await page.context.new_page()
    assert not window._new_tabs


@pytest.mark.asyncio
async def test_a_late_tab_is_not_switched_to_after_a_script_action(session: NotteSession, site: str) -> None:
    async with session.window.page.context.expect_page() as opened:
        _ = await click(session, "late-timer-tab")
    _ = await opened.value
    _ = await session.aexecute(type="evaluate_js", code="document.title")
    observation = await session.aobserve()
    assert observation.metadata.url == f"{site}/"


@pytest.mark.asyncio
async def test_a_click_that_loads_a_page_waits_for_what_it_renders_after_its_load(
    session: NotteSession, site: str
) -> None:
    _ = await click(session, "next")
    assert session.window.page.url == f"{site}/next"
    assert "Rendered after load" in await text(session)


@pytest.mark.asyncio
async def test_a_click_that_loads_a_page_waits_for_what_it_fetches_on_a_timer_after_its_load(
    session: NotteSession, site: str
) -> None:
    # the page has loaded and is quiet before its timer fetches what it renders
    _ = await click(session, "product")
    assert session.window.page.url == f"{site}/product"
    assert "Add to cart" in await text(session)


@pytest.mark.asyncio
async def test_a_click_that_loads_a_page_waits_for_its_request_after_a_cors_preflight(
    session: NotteSession, site: str
) -> None:
    # the request is reported 400 ms after the one before it ended, once its preflight has answered
    _ = await click(session, "api-product")
    assert session.window.page.url == f"{site}/api-product"
    assert "Add to cart" in await text(session)


@pytest.mark.asyncio
async def test_a_goto_waits_for_what_the_page_fetches_after_its_load(session: NotteSession, site: str) -> None:
    # its content arrives 1.2 s after its load: after the fixed waits that followed a goto
    result = await session.aexecute(type="goto", url=f"{site}/app")
    assert result.success
    assert "App content" in await text(session)


@pytest.mark.asyncio
async def test_a_goto_shares_one_timeout_between_its_commit_and_its_page(session: NotteSession, site: str) -> None:
    # the page answers after 0.8 s, then never loads: the wait for it gets what is left of the goto's timeout
    test_config = config.model_copy(update={"timeout_goto_ms": 2_000})
    start = time.monotonic()
    with patch.object(window_module, "config", test_config), patch.object(settle_module, "config", test_config):
        result = await session.aexecute(type="goto", url=f"{site}/slow-stalled")
    elapsed = time.monotonic() - start
    assert result.success
    assert "Stalled" in await text(session)
    assert elapsed < 2.4


@pytest.mark.asyncio
async def test_a_download_tab_closing_does_not_fail_the_click_or_replace_the_page(session: NotteSession) -> None:
    page = session.window.page
    async with page.expect_download() as event:
        _ = await click(session, "download")
    assert (await event.value).suggested_filename == "result.txt"
    assert session.window.page is page
    assert not page.is_closed()


@pytest.mark.asyncio
async def test_requests_with_different_queries_are_all_waited_for(session: NotteSession) -> None:
    _ = await click(session, "pages")
    assert "Both pages fetched" in await text(session)


@pytest.mark.asyncio
async def test_a_repeated_request_is_still_waited_for_while_it_runs(session: NotteSession) -> None:
    _ = await click(session, "retry")
    assert "Retried result" in await text(session)


@pytest.mark.asyncio
async def test_a_goto_that_commits_after_the_settle_cap_still_waits_for_its_page(
    session: NotteSession, site: str
) -> None:
    result = await session.aexecute(type="goto", url=f"{site}/slow-commit")
    assert result.success
    assert "Slow page content" in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("same_document", [False, True])
async def test_a_goto_settles_after_tracker_startup_times_out(
    session: NotteSession, site: str, monkeypatch: pytest.MonkeyPatch, same_document: bool
) -> None:
    if same_document:
        await session.window.page.wait_for_timeout(LONG_GRACE_MS + 100)
        await session.window.page.evaluate(
            """window.addEventListener('hashchange', () => setTimeout(() =>
                document.body.insertAdjacentHTML('beforeend', '<p>Hash route content</p>'), 800), { once: true })"""
        )
    original = Page.evaluate_handle
    blocked = asyncio.Event()
    cancelled = asyncio.Event()

    async def evaluate_handle(page: Page, expression: str) -> JSHandle:
        if expression == settle_module.SETTLE_TRACKER_JS and not blocked.is_set():
            blocked.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return await original(page, expression)

    monkeypatch.setattr(Page, "evaluate_handle", evaluate_handle)
    target = f"{site}#details" if same_document else f"{site}/next"
    async with asyncio.timeout(5):
        result = await session.aexecute(type="goto", url=target)
    assert result.success
    assert blocked.is_set() and cancelled.is_set()
    assert session.window.page.url == f"{site}/{'#details' if same_document else 'next'}"
    assert ("Hash route content" if same_document else "Rendered after load") in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("startup_timeout", [False, True])
async def test_a_hash_goto_redirect_waits_for_the_destination_load_and_render(
    session: NotteSession, site: str, monkeypatch: pytest.MonkeyPatch, startup_timeout: bool
) -> None:
    await session.window.page.evaluate(
        """window.addEventListener('hashchange', () => setTimeout(() =>
            location.href = '/redirect-load', 100), { once: true })"""
    )
    if startup_timeout:
        original = Page.evaluate_handle
        blocked = False

        async def evaluate_handle(page: Page, expression: str) -> JSHandle:
            nonlocal blocked
            if expression == settle_module.SETTLE_TRACKER_JS and not blocked:
                blocked = True
                await asyncio.Event().wait()
            return await original(page, expression)

        monkeypatch.setattr(Page, "evaluate_handle", evaluate_handle)
    result = await session.aexecute(type="goto", url=f"{site}/#redirect")
    assert result.success
    assert session.window.page.url == f"{site}/redirect-load"
    assert "Rendered after redirect load" in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_until", [None, "load"])
@pytest.mark.parametrize(
    "target",
    [
        "https://hash-route.notte.test/#details",
        "https://hash-route.notte.test#details",
        "hash-route.notte.test#details",
        "https://HASH-ROUTE.NOTTE.TEST:443/path/../#details",
    ],
)
async def test_a_hash_route_goto_waits_for_its_delayed_render(
    session: NotteSession, target: str, wait_until: Literal["load"] | None
) -> None:
    # Let the browser canonicalize equivalent URLs, including the https scheme added by BrowserWindow.goto.
    await session.window.page.route(
        "https://hash-route.notte.test/**", lambda route: route.fulfill(body=HOME, content_type="text/html")
    )
    await session.window.page.goto("https://hash-route.notte.test/")
    # The existing document loaded long ago, so its load event cannot provide a new grace window.
    await session.window.page.wait_for_timeout(LONG_GRACE_MS + 100)
    await session.window.page.evaluate(
        """window.addEventListener('hashchange', () => setTimeout(() =>
            document.body.insertAdjacentHTML('beforeend', '<p>Hash route content</p>'), 800), { once: true })"""
    )
    result = await session.aexecute(type="goto", url=target, wait_until=wait_until)
    assert result.success
    assert session.window.page.url == "https://hash-route.notte.test/#details"
    assert "Hash route content" in await text(session)


@pytest.mark.asyncio
async def test_enter_waits_for_the_submitted_page_within_the_bound(session: NotteSession, site: str) -> None:
    await session.window.page.focus("#q")
    start = time.monotonic()
    result = await session.aexecute(PressKeyAction(key="Enter"), raise_on_failure=True)
    elapsed = time.monotonic() - start
    assert result.success
    assert session.window.page.url == f"{site}/results?q=lamp"
    assert "First result" in await text(session)
    # the request it keeps open is waited for as a click's, at most until the cap
    assert elapsed < PAGE_DELAY_S + CAP_MS / 1000 + 1 < config.timeout_goto_ms / 1000


@pytest.mark.asyncio
@pytest.mark.parametrize("submit", ["enter", "click"])
async def test_a_submitted_page_is_waited_for_until_it_rendered_its_data(
    session: NotteSession, site: str, submit: str
) -> None:
    await session.window.page.goto(f"{site}/search")
    if submit == "enter":
        await session.window.page.focus("#query")
        assert (await session.aexecute(PressKeyAction(key="Enter"), raise_on_failure=True)).success
    else:
        _ = await click(session, "submit")
    assert session.window.page.url == f"{site}/search-results?q=lamp"
    assert "Lamp results" in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "bound_ms"),
    [
        # a clock and a carousel: the same nodes change every 100 ms
        ("clock", SETTLE_MS),
        # a request the page sends every 300 ms
        ("polling", CAP_MS / 2),
        # a request in a frame of another origin
        ("ad-page", CAP_MS / 2),
    ],
)
async def test_what_a_page_does_on_its_own_is_not_waited_for(
    session: NotteSession, site: str, path: str, bound_ms: float
) -> None:
    await session.window.page.goto(f"{site}/{path}", wait_until="load")
    elapsed = await click(session, "nothing")
    assert elapsed < bound_ms / 1000


@pytest.mark.asyncio
async def test_a_scroll_waits_for_what_it_loads(session: NotteSession, site: str) -> None:
    await session.window.page.goto(f"{site}/feed", wait_until="load")
    await session.window.page.mouse.move(100, 100)
    assert (await session.aexecute(ScrollDownAction(amount=5000), raise_on_failure=True)).success
    assert "More items" in await text(session)


@pytest.mark.asyncio
async def test_a_navigation_a_timer_starts_is_waited_for(session: NotteSession, site: str) -> None:
    _ = await click(session, "timer-nav")
    assert session.window.page.url == f"{site}/next"
    assert "Rendered after load" in await text(session)


@pytest.mark.asyncio
async def test_a_client_side_navigation_a_timer_starts_is_waited_for_until_it_rendered(
    session: NotteSession, site: str
) -> None:
    _ = await click(session, "spa")
    assert session.window.page.url == f"{site}/spa"
    assert "Spa page" in await text(session)


@pytest.mark.asyncio
async def test_a_client_side_navigation_waits_for_the_code_it_loads(session: NotteSession, site: str) -> None:
    # the route's code takes 800 ms: longer than the grace of a click whose only change is the script it adds
    _ = await click(session, "route")
    assert session.window.page.url == f"{site}/contact"
    assert "Contact page" in await text(session)


@pytest.mark.asyncio
async def test_a_dom_change_after_a_request_is_waited_for(session: NotteSession) -> None:
    # the request takes 700 ms: longer than the fixed 500 ms wait that followed a click
    _ = await click(session, "fetch")
    assert "Fetched result" in await text(session)


@pytest.mark.asyncio
async def test_a_click_with_no_visible_effect_keeps_the_grace_window(session: NotteSession) -> None:
    elapsed = await click(session, "nothing")
    assert elapsed >= LONG_GRACE_MS / 1000
    # a change that starts within it (here after 400 ms) is waited for
    _ = await click(session, "late")
    assert "Late result" in await text(session)


@pytest.mark.asyncio
async def test_scrape_and_screenshot_right_after_a_navigating_click_see_the_new_page(session: NotteSession) -> None:
    _ = await click(session, "next")
    assert "Rendered after load" in await session.ascrape()
    screenshot = Image.open(io.BytesIO((await session.ascreenshot()).raw)).convert("RGB")
    red, green, blue = screenshot.getpixel((screenshot.width // 2, screenshot.height // 2))  # pyright: ignore[reportGeneralTypeIssues]
    assert red > 200 and green < 60 and blue < 60


@pytest.mark.asyncio
@pytest.mark.parametrize("element", ["hang", "hang-page"])
async def test_a_request_that_never_ends_is_waited_for_within_the_bound(
    session: NotteSession, site: str, element: str
) -> None:
    elapsed = await click(session, element)
    if element == "hang":
        assert elapsed < CAP_MS / 1000 + 1
    else:
        assert session.window.page.url == f"{site}/hanging"
        assert "Hanging" in await text(session)
        assert elapsed < PAGE_DELAY_S + CAP_MS / 1000 + 1 < config.timeout_goto_ms / 1000


@pytest.mark.asyncio
async def test_back_and_forward_wait_for_the_page_they_load(site: str) -> None:
    # without the back-forward cache, a back / forward loads the page again
    async with NotteSession(headless=True, chrome_args=["--disable-back-forward-cache"]) as session:
        _ = await session.aexecute(type="goto", url=f"{site}/", wait_until="load")
        _ = await click(session, "next")
        assert (await session.aexecute(GoBackAction(), raise_on_failure=True)).success
        assert session.window.page.url == f"{site}/"
        assert await session.window.page.evaluate("document.readyState") == "complete"
        assert (await session.aexecute(GoForwardAction(), raise_on_failure=True)).success
        assert session.window.page.url == f"{site}/next"
        assert "Rendered after load" in await text(session)


@pytest.mark.asyncio
async def test_a_scroll_ends_once_its_position_is_stable(session: NotteSession) -> None:
    # the page keeps scrolling for 300 ms after the wheel (a smooth-scroll script)
    await session.window.page.set_content('<div style="height:6000px">Long page</div>')
    await session.window.page.evaluate("""() => {
        let animating = false;
        window.addEventListener('scroll', () => {
            if (animating) return;
            animating = true;
            const end = performance.now() + 300;
            const step = () => { if (performance.now() < end) { window.scrollBy(0, 10); requestAnimationFrame(step); } };
            requestAnimationFrame(step);
        });
    }""")
    await session.window.page.mouse.move(100, 100)
    start = time.monotonic()
    assert (await session.aexecute(ScrollDownAction(amount=250), raise_on_failure=True)).success
    elapsed = time.monotonic() - start
    ended = await session.window.page.evaluate("window.scrollY")
    await session.window.page.wait_for_timeout(300)
    assert await session.window.page.evaluate("window.scrollY") == ended
    # waited for the animation, not for a fixed delay past it
    assert 0.3 <= elapsed < 1


@pytest.mark.asyncio
async def test_the_grace_counts_from_when_a_slow_click_lands(session: NotteSession, site: str) -> None:
    await session.window.page.goto(f"{site}/covered")
    # the button is covered for 700 ms: the click waits for it, then its effect starts 300 ms later
    _ = await click(session, "covered")
    assert "Covered result" in await text(session)


@pytest.mark.asyncio
async def test_pre_action_activity_does_not_consume_the_grace_without_an_input_event(session: NotteSession) -> None:
    # Scroll has no pointer/key event to reset the tracker; its grace starts when the action ends.
    settle = await PageSettle.start(session.window.page)
    try:
        await session.window.page.evaluate("document.body.append(document.createElement('hr'))")
        await session.window.page.wait_for_timeout(QUIET_MS + 50)
        await session.window.page.evaluate(
            """setTimeout(() => document.body.insertAdjacentHTML('beforeend', '<p>Result after action</p>'), 200)"""
        )
        settle.acted()
        await settle.wait(grace_ms=LONG_GRACE_MS)
        assert "Result after action" in await text(session)
    finally:
        await settle.close()


@pytest.mark.asyncio
async def test_rendering_that_spans_a_scroll_action_still_needs_a_quiet_page(session: NotteSession) -> None:
    settle = await PageSettle.start(session.window.page)
    try:
        await session.window.page.evaluate(
            """() => {
                document.body.append(document.createElement('hr'));
                for (const delay of [100, 200, 300]) {
                    setTimeout(() => document.body.append(document.createElement('hr')), delay);
                }
                setTimeout(() => document.body.insertAdjacentHTML('beforeend', '<p>Rendering finished</p>'), 400);
            }"""
        )
        settle.acted()
        await settle.wait()
        assert "Rendering finished" in await text(session)
    finally:
        await settle.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("link", ["late-load", "late-load-timer"])
async def test_a_page_that_loads_after_it_settled_is_watched_from_its_load(
    session: NotteSession, site: str, link: str
) -> None:
    _ = await click(session, link)
    assert session.window.page.url == f"{site}/{link}"
    assert "Rendered after a late load" in await text(session)


@pytest.mark.asyncio
async def test_a_shadow_root_the_action_adds_is_watched(session: NotteSession) -> None:
    # it renders in it in two steps, the second one after the quiet window of the first change, the insertion
    _ = await click(session, "widget")
    assert await session.window.page.evaluate("document.querySelector('x-widget').shadowRoot.textContent") == (
        "Widget content"
    )


@pytest.mark.asyncio
async def test_the_document_a_frame_navigates_to_is_watched(session: NotteSession) -> None:
    _ = await click(session, "frame")
    assert "Frame content" in await session.window.page.frame_locator("#inner").locator("body").inner_text()


@pytest.mark.asyncio
async def test_a_new_tab_is_tracked_from_when_it_appears(session: NotteSession, site: str) -> None:
    _ = await click(session, "fetching-tab")
    assert session.window.page.url == f"{site}/fetching-tab"
    assert "Fetched in the tab" in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [True, False])
async def test_a_closing_page_waits_for_its_replacement_if_it_opens_one(
    session: NotteSession, site: str, replacement: bool
) -> None:
    # A script-opened page can close itself, unlike the initial page of a browser context. `close-self` closes it
    # right after the click returns: a close the driver reports before acknowledging the click is an error unless a
    # tab replaces it (`test_a_click_reporting_a_closed_target_requires_a_live_replacement`)
    async with session.window.page.context.expect_page() as opened:
        await session.window.page.evaluate("window.open('/')")
    original = await opened.value
    await original.wait_for_load_state("load")
    session.window.page = original
    closed_at: float | None = None

    def record_close(_page: Page) -> None:
        nonlocal closed_at
        closed_at = time.monotonic()

    original.once("close", record_close)
    if not replacement:
        # Waiting for click actionability is separate from waiting for a tab after the original closes.
        await original.evaluate("""() => {
            const cover = document.createElement('div');
            cover.style.cssText = 'position:fixed;inset:0;z-index:1000';
            document.body.append(cover);
            setTimeout(() => cover.remove(), 1800);
        }""")
    _ = await click(session, "replace-self" if replacement else "close-self")
    assert original.is_closed()
    assert closed_at is not None
    if replacement:
        assert session.window.page.url == f"{site}/fetching-tab"
        assert "Fetched in the tab" in await text(session)
    else:
        assert session.window.page.url == f"{site}/"
        assert time.monotonic() - closed_at < LONG_GRACE_MS / 1000 + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["new", "opener", "none"])
async def test_a_click_reporting_a_closed_target_requires_a_live_replacement(
    session: NotteSession, site: str, monkeypatch: pytest.MonkeyPatch, replacement: str
) -> None:
    opener = session.window.page
    async with opener.context.expect_page() as opened:
        await opener.evaluate("window.open('/')")
    original = await opened.value
    await original.wait_for_load_state("load")
    if replacement == "none":
        await opener.close()
    elif replacement == "opener":
        await original.locator("#close-self").evaluate(
            "el => el.onclick = () => { window.opener.location.href = '/fetching-tab'; window.close(); }"
        )
    session.window.page = original
    original_click = Locator.click

    async def click_then_report_closed(locator: Locator, *, timeout: float) -> None:
        await original_click(locator, timeout=timeout)
        if not original.is_closed():
            await original.wait_for_event("close")
        # Patchright can report the handler's window.close() before acknowledging the click.
        raise Error("Locator.click: Target page, context or browser has been closed")

    monkeypatch.setattr(Locator, "click", click_then_report_closed)
    if replacement != "none":
        _ = await click(session, "replace-self" if replacement == "new" else "close-self")
        assert original.is_closed()
        if replacement == "opener":
            assert session.window.page is opener
        assert session.window.page.url == f"{site}/fetching-tab"
        assert "Fetched in the tab" in await text(session)
    else:
        with pytest.raises(NotteBaseError, match="Target page, context or browser has been closed"):
            _ = await click(session, "close-self")


@pytest.mark.asyncio
@pytest.mark.parametrize("report_closed", [False, True])
@pytest.mark.parametrize("unrelated_tab", [False, True])
async def test_a_closing_click_waits_for_a_request_it_started_on_an_existing_tab(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch, report_closed: bool, unrelated_tab: bool
) -> None:
    opener = session.window.page
    await opener.evaluate("""() => {
        window.fetchResult = () => fetch('/data?delay=2').then(() =>
            document.body.insertAdjacentHTML('beforeend', '<p>Fetched on the opener</p>'));
    }""")
    async with opener.context.expect_page() as opened:
        await opener.evaluate("window.open('/')")
    popup = await opened.value
    await popup.wait_for_load_state("load")
    await popup.locator("#close-self").evaluate(
        "el => el.onclick = () => { window.opener.fetchResult(); window.close(); }"
    )
    other: Page | None = None
    if unrelated_tab:
        other = await opener.context.new_page()
        await other.goto(opener.url)
    session.window.page = popup
    original_click = Locator.click

    async def closing_click(locator: Locator, *, timeout: float) -> None:
        await original_click(locator, timeout=timeout)
        if other is not None:
            # An unrelated iframe navigation must not be mistaken for a replacement page.
            await other.locator("#inner").evaluate("el => { el.src = '/inner'; }")
        if not popup.is_closed():
            await popup.wait_for_event("close")
        if report_closed:
            raise Error("Locator.click: Target page, context or browser has been closed")

    monkeypatch.setattr(Locator, "click", closing_click)
    async with opener.expect_request("**/data?delay=2"):
        _ = await click(session, "close-self")
    assert popup.is_closed()
    assert session.window.page is opener
    assert "Fetched on the opener" in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", ["/fetching-tab", "/slow-second"])
@pytest.mark.parametrize("report_closed", [False, True])
async def test_a_closing_popup_selects_the_existing_named_tab_it_navigated(
    session: NotteSession, site: str, monkeypatch: pytest.MonkeyPatch, destination: str, report_closed: bool
) -> None:
    opener = session.window.page
    # The slow case reloads the same URL: the request identifies it before its URL or document changes.
    initial = destination if destination == "/slow-second" else "/second"
    async with opener.context.expect_page() as opened:
        await opener.evaluate("url => window.open(url, 'results')", f"{site}{initial}")
    results = await opened.value
    await results.wait_for_load_state("load")
    async with opener.context.expect_page() as opened:
        await opener.evaluate("window.open('/', 'helper')")
    popup = await opened.value
    await popup.wait_for_load_state("load")
    await popup.locator("#close-self").evaluate(
        "(el, url) => el.onclick = () => { window.open(url, 'results'); window.close(); }", destination
    )
    session.window.page = popup
    original_click = Locator.click

    async def closing_click(locator: Locator, *, timeout: float) -> None:
        await original_click(locator, timeout=timeout)
        if not popup.is_closed():
            await popup.wait_for_event("close")
        if report_closed:
            raise Error("Locator.click: Target page, context or browser has been closed")

    monkeypatch.setattr(Locator, "click", closing_click)
    async with results.expect_request(f"{site}{destination}"):
        _ = await click(session, "close-self")
    assert popup.is_closed()
    assert session.window.page is results
    assert len(opener.context.pages) == 2
    assert results.url == f"{site}{destination}"
    expected = "Fetched in the tab" if destination == "/fetching-tab" else "Second tab"
    assert expected in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("report_closed", [False, True])
async def test_a_closing_popup_ignores_other_tabs_navigating_during_element_lookup(
    session: NotteSession, site: str, monkeypatch: pytest.MonkeyPatch, report_closed: bool
) -> None:
    opener = session.window.page
    async with opener.context.expect_page() as opened:
        await opener.evaluate("window.open('/')")
    popup = await opened.value
    await popup.wait_for_load_state("load")
    await popup.locator("#close-self").evaluate("el => el.onclick = () => window.close()")
    other = await opener.context.new_page()
    await other.goto(site)
    session.window.page = popup
    original_locate = execution_module._locate  # pyright: ignore[reportPrivateUsage]
    original_click = Locator.click

    async def locate_with_unrelated_navigation(
        window: BrowserWindow, action: InteractionAction, snapshot: BrowserSnapshot | None
    ) -> Locator:
        locator = await original_locate(window, action, snapshot)
        await other.goto(f"{site}/second")
        return locator

    async def closing_click(locator: Locator, *, timeout: float) -> None:
        await original_click(locator, timeout=timeout)
        if not popup.is_closed():
            await popup.wait_for_event("close")
        if report_closed:
            raise Error("Locator.click: Target page, context or browser has been closed")

    monkeypatch.setattr(execution_module, "_locate", locate_with_unrelated_navigation)
    monkeypatch.setattr(Locator, "click", closing_click)
    _ = await click(session, "close-self")
    assert popup.is_closed()
    assert other.url == f"{site}/second"
    assert session.window.page is opener


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["native", "closed", "js"])
@pytest.mark.parametrize("replacement", ["opener", "named"])
@pytest.mark.parametrize("framed", [False, True])
async def test_a_closing_popup_ignores_navigation_during_click_actionability(
    session: NotteSession, site: str, monkeypatch: pytest.MonkeyPatch, mode: str, replacement: str, framed: bool
) -> None:
    opener = session.window.page
    results: Page | None = None
    if replacement == "named":
        async with opener.context.expect_page() as opened:
            await opener.evaluate("window.open('/second', 'results')")
        results = await opened.value
        await results.wait_for_load_state("load")
    async with opener.context.expect_page() as opened:
        await opener.evaluate("window.open('/')")
    popup = await opened.value
    await popup.wait_for_load_state("load")
    if framed:
        await popup.set_content('<iframe id="click-frame" src="/"></iframe>')
        target = popup.frame_locator("#click-frame").locator("#close-self")
        cover = popup.frame_locator("#click-frame").locator("#cover")
    else:
        target = popup.locator("#close-self")
        cover = popup.locator("#cover")
    await target.evaluate(
        """(el, named) => {
            el.onclick = () => { if (named) top.open('/slow-second', 'results'); top.close(); };
            const cover = document.createElement('div');
            cover.id = 'cover';
            cover.style = 'position: fixed; inset: 0; background: white; z-index: 9999';
            document.body.append(cover);
        }""",
        replacement == "named",
    )
    other = await opener.context.new_page()
    await other.goto(site)
    session.window.page = popup
    original_click = Locator.click

    async def covered_click(locator: Locator, *, timeout: float) -> None:
        if mode == "js":
            await other.goto(f"{site}/second")
            await cover.evaluate("el => el.remove()")
            raise PlaywrightTimeoutError("Use the JS click fallback")
        pending = asyncio.create_task(original_click(locator, timeout=timeout))
        try:
            await other.goto(f"{site}/second")
            assert not pending.done(), "The covered button must still be waiting for input"
            await cover.evaluate("el => el.remove()")
            await pending
        finally:
            if not pending.done():
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
        if not popup.is_closed():
            await popup.wait_for_event("close")
        if mode == "closed":
            raise Error("Locator.click: Target page, context or browser has been closed")

    monkeypatch.setattr(Locator, "click", covered_click)
    result = await session.aexecute(
        type="click",
        id="click",
        selector={
            "css_selector": "#close-self",
            "in_iframe": framed,
            "iframe_parent_css_selectors": ["#click-frame"] if framed else [],
        },
    )
    assert result.success, result.message
    assert popup.is_closed()
    assert session.window.page is (results if results is not None else opener)
    if results is not None:
        assert results.url == f"{site}/slow-second"
        assert "Second tab" in await text(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["native", "closed", "js"])
async def test_replacement_selection_waits_for_click_input_delivery(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    opener = session.window.page
    async with opener.context.expect_page() as opened:
        await opener.evaluate("window.open('/')")
    popup = await opened.value
    await popup.wait_for_load_state("load")
    await popup.locator("#close-self").evaluate(
        "el => el.onclick = () => { window.opener.document.body.dataset.clicked = 'yes'; window.close(); }"
    )
    session.window.page = popup
    notification_started, release, native_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    notify = execution_module._ClickInputBinding.notify  # pyright: ignore[reportPrivateUsage]
    original_click = Locator.click
    settlement = AsyncMock()

    async def delayed_notify(
        binding: execution_module._ClickInputBinding,
        token: str,  # pyright: ignore[reportPrivateUsage]
    ) -> None:
        notification_started.set()
        await release.wait()
        notify(binding, token)

    async def closing_click(locator: Locator, *, timeout: float) -> None:
        try:
            if mode == "js":
                raise PlaywrightTimeoutError("Use the JS click fallback")
            await original_click(locator, timeout=timeout)
        finally:
            native_done.set()
        if mode == "closed":
            raise Error("Locator.click: Target page, context or browser has been closed")

    monkeypatch.setattr(execution_module._ClickInputBinding, "notify", delayed_notify)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(Locator, "click", closing_click)
    monkeypatch.setattr(execution_module, "_settle", settlement)
    pending = asyncio.create_task(click(session, "close-self"))
    try:
        await notification_started.wait()
        await native_done.wait()
        clicked = await opener.locator("body").get_attribute("data-clicked")
        assert clicked == (None if mode == "js" else "yes")
        settlement.assert_not_awaited()
        assert popup.is_closed() is (mode != "js")
        release.set()
        _ = await pending
        assert popup.is_closed()
        assert session.window.page is opener
    finally:
        release.set()
        if not pending.done():
            pending.cancel()
        with suppress(asyncio.CancelledError):
            await pending


@pytest.mark.asyncio
async def test_click_input_resources_do_not_accumulate_between_actions(session: NotteSession) -> None:
    page = session.window.page
    other = await page.context.new_page()
    await other.goto(page.url)
    # Prime the full click path: the driver lazily installs a persistent hit-target interceptor.
    _ = await click(session, "nothing")
    cdp = await page.context.new_cdp_session(page)

    async def pointer_listeners() -> int:
        result = await cdp.send("Runtime.evaluate", {"expression": "window"})
        listeners = await cdp.send("DOMDebugger.getEventListeners", {"objectId": result["result"]["objectId"]})
        return sum(listener["type"] == "pointerdown" for listener in listeners["listeners"])

    try:
        before = await pointer_listeners()
        names: list[str] | None = None
        for _ in range(2):
            _ = await click(session, "nothing")
            assert await pointer_listeners() == before
            current = await evaluate_in_main_world(
                page.main_frame,
                "() => Object.getOwnPropertyNames(window).filter(name => name.startsWith('__notte_click_'))",
            )
            assert len(current) == 1
            if names is not None:
                assert current == names
            names = current
    finally:
        await cdp.detach()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["page", "browser", "unclosed", "unusable", "missing-input"])
async def test_a_closed_target_error_is_not_hidden_by_an_unusable_replacement(
    session: NotteSession, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    opener = session.window.page
    async with opener.context.expect_page() as opened:
        await opener.evaluate("window.open('/')")
    original = await opened.value
    await original.wait_for_load_state("load")
    session.window.page = original

    async def fail_click(locator: Locator, *, timeout: float) -> None:
        if failure == "page":
            await opener.close()
            await original.close()
        elif failure == "browser":
            browser = original.context.browser
            assert browser is not None
            await browser.close()
        elif failure in ("unusable", "missing-input"):
            await original.close()
        raise Error("Locator.click: Target page, context or browser has been closed")

    monkeypatch.setattr(Locator, "click", fail_click)
    if failure == "unusable":
        monkeypatch.setattr(
            opener, "evaluate", AsyncMock(side_effect=Error("Target page, context or browser has been closed"))
        )
    with pytest.raises(NotteBaseError, match="Target page, context or browser has been closed"):
        _ = await click(session, "close-self")


@pytest.mark.asyncio
async def test_the_shadow_roots_in_a_new_shadow_root_are_watched(session: NotteSession) -> None:
    _ = await click(session, "nested")
    inner = "document.querySelector('x-outer').shadowRoot.querySelector('x-inner').shadowRoot.textContent"
    assert await session.window.page.evaluate(inner) == "Inner content"


@pytest.mark.asyncio
async def test_a_tab_that_opens_as_another_closes_is_switched_to(session: NotteSession, site: str) -> None:
    async with session.window.page.context.expect_page() as helper:
        # the page's own script keeps a handle on it (not through execute(), which would switch to it)
        await session.window.page.click("#open-helper")
    await (await helper.value).wait_for_load_state("load")
    assert len(session.window.page.context.pages) == 2
    _ = await click(session, "swap-tab")
    assert len(session.window.page.context.pages) == 2
    assert session.window.page.url == f"{site}/second"
    assert "Second tab" in await text(session)
