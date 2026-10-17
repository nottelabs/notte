import asyncio
import json
import os
import sys
from urllib.parse import urlsplit

from lmnr import Laminar
from notte_sdk import NotteClient
from playwright.async_api import async_playwright


async def read_page(url: str = "https://example.com") -> dict[str, str]:
    with NotteClient().Session(max_duration_minutes=3) as session:
        with Laminar.start_as_current_span(
            name="notte.read_page", input={"host": urlsplit(url).hostname}, session_id=session.session_id
        ) as span:
            stage = "browser connection"
            try:
                async with async_playwright() as driver:
                    browser = await driver.chromium.connect_over_cdp(session.cdp_url())
                    try:
                        page = await browser.contexts[0].new_page()
                        stage = "navigation"
                        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        stage = "reading the title"
                        result = {"title": await page.title(), "session_id": session.session_id}
                        Laminar.set_span_output(result)
                        return {**result, "trace_id": format(span.get_span_context().trace_id, "032x")}
                    finally:
                        failure = sys.exception()
                        try:
                            await asyncio.wait_for(browser.close(), timeout=5)
                        except Exception:
                            if failure is None:
                                raise RuntimeError("Browser cleanup failed") from None
            except Exception:
                trace_id = format(span.get_span_context().trace_id, "032x")
                raise RuntimeError(
                    f"Notte browser task failed during {stage} (session {session.session_id}, trace {trace_id})"
                ) from None


if __name__ == "__main__":
    Laminar.initialize(project_api_key=os.environ["LMNR_PROJECT_API_KEY"], instruments=set())
    try:
        print(json.dumps(asyncio.run(read_page(sys.argv[1] if len(sys.argv) > 1 else "https://example.com"))))
    finally:
        Laminar.shutdown()
