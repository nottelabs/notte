import asyncio
import json
import os
import sys

from braintrust import init_logger
from notte_sdk import NotteClient


async def run_demo(url: str = "https://example.com") -> dict:
    if not os.environ.get("BRAINTRUST_API_KEY"):
        raise RuntimeError("Set BRAINTRUST_API_KEY")
    logger = init_logger(project=os.getenv("BRAINTRUST_PROJECT", "notte-integration-tests"))
    client = NotteClient()
    session_id = "not-created"
    stage = "create browser"
    try:
        with logger.start_span(name="notte.browser", input={"url": url}) as span:
            try:
                async with client.Session(max_duration_minutes=3) as session:
                    session_id = session.session_id
                    span.log(metadata={"session_id": session_id})
                    stage = "navigate"
                    page = await session.apage
                    await page.goto(url, timeout=30_000)
                    title = await page.title()
                span.log(output={"title": title})
                return {"title": title, "session_id": session_id, "span_id": span.id, "trace_url": span.permalink()}
            except Exception:
                raise RuntimeError(f"Browser task failed: {stage} (session {session_id})") from None
    finally:
        logger.flush()


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(run_demo(sys.argv[1] if len(sys.argv) > 1 else "https://example.com"))))
    except Exception as error:
        print(str(error))
        raise SystemExit(1) from None
