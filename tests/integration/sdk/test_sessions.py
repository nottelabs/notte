import pytest
from dotenv import load_dotenv
from notte_core.common.config import BrowserType
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError

_ = load_dotenv()


def test_start_close_session():
    client = NotteClient()

    response = client.sessions.start(proxies=False)
    assert response.status == "active"
    response = client.sessions.stop(session_id=response.session_id)
    assert response.status == "closed"


def test_start_close_session_factory():
    client = NotteClient()
    with client.Session(proxies=False) as session:
        assert session.session_id is not None
        status = session.status()
        assert status.status == "active"
    assert session.response is not None
    assert session.response.status == "closed"


def test_start_close_session_with_proxy():
    client = NotteClient()
    with client.Session(proxies=True) as session:
        assert session.session_id is not None
        status = session.status()
        assert status.status == "active"
    assert session.response is not None


def test_start_session_with_too_small_viewport_is_rejected():
    client = NotteClient()
    with pytest.raises(NotteAPIError) as exc_info:
        with client.Session(proxies=False, viewport_height=100, viewport_width=100):
            pass
    assert 400 <= exc_info.value.status_code < 500


def test_start_close_session_with_viewport():
    client = NotteClient()
    with client.Session(proxies=False, viewport_height=768, viewport_width=1024) as session:
        assert session.session_id is not None
        status = session.status()
        assert status.status == "active"
    assert session.response is not None


def test_replay_session():
    client = NotteClient()
    with client.Session(proxies=False, open_viewer=False) as session:
        _ = session.execute(type="goto", url="https://www.google.com")
        _ = session.execute(type="wait", time_ms=3_000)
    response = client.sessions.replay(session_id=session.session_id)
    assert response.expires_at
    assert response.mp4_url or response.playlist_content


@pytest.mark.parametrize("browser_type", ["chrome", "chromium"])
def test_start_close_session_with_browser_type(browser_type: BrowserType):
    client = NotteClient()
    with client.Session(proxies=False, open_viewer=False, browser_type=browser_type) as session:
        assert session.session_id is not None
        status = session.status()
        assert status.status == "active"
    assert session.response is not None


def test_scroll_moves_the_hosted_page_and_returns_to_start():
    client = NotteClient()
    fixture_url = "https://scroll-fixture.notte.test/"
    with client.Session(proxies=False, viewport_width=1280, viewport_height=800) as session:
        page = session.page

        def serve_fixture(route):
            if route.request.url == fixture_url:
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="<!doctype html><style>html {scroll-behavior:auto} body {margin:0}</style>"
                    '<main style="height:300vh">Scrollable fixture</main>',
                )
            else:
                route.abort()

        page.route("**/*", serve_fixture)
        # Keep the synchronous Playwright event loop running for route callbacks.
        _ = page.goto(fixture_url, wait_until="domcontentloaded")
        assert page.evaluate("document.scrollingElement.scrollHeight > window.innerHeight")

        for selector in (None, "html"):
            start = page.evaluate("window.scrollY")
            down = session.execute(type="scroll_down", selector=selector)
            after_down = page.evaluate("window.scrollY")
            assert down.success
            assert after_down > start, f"Scroll did not move the page (selector={selector!r})"

            up = session.execute(type="scroll_up", selector=selector)
            assert up.success
            assert page.evaluate("window.scrollY") == start

        page.set_content("<!doctype html><p>No scrolling here</p>")
        failed = session.execute(type="scroll_down", raise_on_failure=False)
        assert not failed.success
        assert failed.exception_detail is not None
        assert failed.exception_detail.error_type == "ScrollActionFailedError"
