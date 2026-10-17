import asyncio
import json
import os
import sys

from braintrust import init_logger
from notte_sdk import NotteClient
from playwright.async_api import async_playwright


class BrowserTaskError(RuntimeError):
    pass


async def run_demo(url: str = "https://example.com") -> dict:
    if not os.environ.get("BRAINTRUST_API_KEY"):
        raise RuntimeError("Set BRAINTRUST_API_KEY")
    logger = init_logger(project=os.getenv("BRAINTRUST_PROJECT", "notte-integration-tests"))
    client = NotteClient()
    session_id = "not-created"
    stage = "create browser"

    def browser_error(error):
        if isinstance(error, BrowserTaskError):
            return error
        category = type(error).__name__
        status = getattr(error, "status_code", None)
        if type(status) is int:
            category += f" HTTP {status}"
        return BrowserTaskError(f"Browser task failed: {stage} [{category}] (session {session_id})")

    try:
        with logger.start_span(name="notte.browser", input={"url": url}) as span:
            try:
                with client.Session(max_duration_minutes=3) as session:
                    session_id = session.session_id
                    span.log(metadata={"session_id": session_id})
                    try:
                        async with async_playwright() as driver:
                            stage = "connect browser"
                            browser = await driver.chromium.connect_over_cdp(session.cdp_url())
                            try:
                                stage = "navigate"
                                page = browser.contexts[0].pages[0]
                                await page.goto(url, timeout=30_000)
                                title = await page.title()
                            finally:
                                failed = sys.exception() is not None
                                if not failed:
                                    stage = "disconnect browser"
                                try:
                                    await asyncio.wait_for(browser.close(), timeout=5)
                                except Exception:
                                    if not failed:
                                        raise RuntimeError("Browser disconnect failed") from None
                        stage = "release browser"
                    except Exception as error:
                        raise browser_error(error) from None
                span.log(output={"title": title})
                return {"title": title, "session_id": session_id, "span_id": span.id, "trace_url": span.permalink()}
            except Exception as error:
                raise browser_error(error) from None
    except Exception as error:
        raise browser_error(error) from None
    finally:
        failed = sys.exception() is not None
        try:
            logger.flush()
        except Exception:
            if not failed:
                raise RuntimeError(f"Braintrust trace flush failed (session {session_id})") from None


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(run_demo(sys.argv[1] if len(sys.argv) > 1 else "https://example.com"))))
    except Exception as error:
        print(str(error))
        raise SystemExit(1) from None
