import asyncio
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from notte_browser.session import NotteSession


@pytest.fixture
def page_url() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Browser works</h1></body></html>")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.asyncio
@pytest.mark.timeout(60, method="thread")
async def test_sync_browser_lifecycle_inside_running_loop(page_url: str) -> None:
    caller_loop = asyncio.get_running_loop()
    session = NotteSession(headless=True)
    with session:
        result = session.execute(type="goto", url=page_url)
        assert result.success
        assert "Browser works" in session.observe().space.description
        assert session.evaluate_js("document.querySelector('h1').textContent") == "Browser works"
        assert session.screenshot().raw
        with pytest.raises(RuntimeError, match="do not mix"):
            await session.aobserve()
        with pytest.raises(RuntimeError, match="do not mix"):
            await session.astop()
    # The caller's loop is still usable and session restart gets a fresh browser.
    await asyncio.sleep(0)
    assert asyncio.get_running_loop() is caller_loop
    with session:
        assert session.execute(type="goto", url=page_url).success


@pytest.mark.asyncio
@pytest.mark.timeout(60, method="thread")
async def test_async_browser_rejects_sync_methods_without_breaking_owner(page_url: str) -> None:
    async with NotteSession(headless=True) as session:
        with pytest.raises(RuntimeError, match="do not mix"):
            session.observe()
        with pytest.raises(RuntimeError, match="do not mix"):
            session.stop()
        assert (await session.aexecute(type="goto", url=page_url)).success
        assert "Browser works" in (await session.aobserve()).space.description
