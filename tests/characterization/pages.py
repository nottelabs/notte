"""Local page loading shared by the snapshot worker and execution tests."""

from pathlib import Path

from notte_browser.session import NotteSession
from patchright.async_api import Route

ROOT = Path(__file__).parent
FIXTURES = ROOT / "fixtures"
PAGES = sorted(path.stem for path in FIXTURES.glob("*.html"))


async def load(session: NotteSession, fixture: str) -> None:
    page = session.window.page
    url = f"http://characterization.test/{fixture}"

    async def serve(route: Route) -> None:
        if route.request.url == url and route.request.resource_type == "document":
            await route.fulfill(
                body=(FIXTURES / f"{fixture}.html").read_text(), content_type="text/html; charset=utf-8"
            )
        else:
            await route.abort()

    await page.route("**/*", serve)
    _ = await page.goto(url, wait_until="load")
    _ = await page.evaluate((FIXTURES / "recorder.js").read_text())
