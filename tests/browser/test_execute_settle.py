"""`execute()` waits until the page has reacted to an action (`notte_browser.settle`), not for fixed delays."""

import asyncio
import io
import socket
import time
from collections.abc import AsyncIterator
from contextlib import closing

import pytest
import pytest_asyncio
from aiohttp import web
from notte_browser.session import NotteSession
from notte_browser.settle import CAP_MS, LONG_GRACE_MS, SETTLE_MS
from notte_core.actions import ClickAction, GoBackAction, GoForwardAction, PressKeyAction, ScrollDownAction
from notte_core.config import config
from PIL import Image

HOME = """<html><body>
<a id="next" href="/next">Next page</a>
<a id="tab" href="/second" target="_blank">Open in a new tab</a>
<button id="later-tab" onclick="setTimeout(() => window.open('/second'), 100)">Open a tab later</button>
<button id="slow-tab" onclick="window.open('/slow-second')">Open a slow tab</button>
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
        await asyncio.sleep(SLOW_PAGE_DELAY_S if request.path.startswith("/slow") else PAGE_DELAY_S)
        # the same server on another host name is another origin
        other_origin = f"http://localhost:{request.url.port}"
        return web.Response(text=PAGES[request.path].replace("OTHER_ORIGIN", other_origin), content_type="text/html")

    async def data(request: web.Request) -> web.Response:
        await asyncio.sleep(float(request.query["delay"]))
        return web.json_response({})

    async def slow_script(_request: web.Request) -> web.Response:
        await asyncio.sleep(0.3)
        return web.Response(text="", content_type="text/javascript")

    async def slow_image(_request: web.Request) -> web.Response:
        await asyncio.sleep(1)
        return web.Response(status=404)

    async def hang(_request: web.Request) -> web.Response:
        await release.wait()
        return web.json_response({})

    app = web.Application()
    for path in PAGES:
        app.router.add_get(path, page)
    app.router.add_get("/data", data)
    app.router.add_get("/slow.js", slow_script)
    app.router.add_get("/slow-image", slow_image)
    app.router.add_get("/hang", hang)
    runner = web.AppRunner(app)
    await runner.setup()
    with closing(socket.socket()) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen()
        await web.SockSite(runner, server_socket).start()
        try:
            yield f"http://127.0.0.1:{server_socket.getsockname()[1]}"
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
async def test_a_click_that_loads_a_page_waits_for_what_it_renders_after_its_load(
    session: NotteSession, site: str
) -> None:
    _ = await click(session, "next")
    assert session.window.page.url == f"{site}/next"
    assert "Rendered after load" in await text(session)


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
