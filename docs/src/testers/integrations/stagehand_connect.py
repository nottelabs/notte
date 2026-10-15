# @sniptest filename=notte_stagehand.py
# @sniptest typecheck_only=true
import asyncio
import os

from notte_sdk import NotteClient
from pydantic import BaseModel
from stagehand import Stagehand, local_browser


class Heading(BaseModel):
    heading: str


async def main() -> None:
    with NotteClient().Session() as session:
        browser = await local_browser.connect(cdp_url=session.cdp_url())
        try:
            stagehand = await Stagehand.create(
                browser=browser,
                model="anthropic/claude-sonnet-4-6",
                model_api_key=os.environ["ANTHROPIC_API_KEY"],
            )
            try:
                page = await browser.context.new_page()
                await page.goto("https://example.com")
                result = await stagehand.extract("Extract the main heading", Heading, page=page)
                print(result.data.heading)
            finally:
                await stagehand.close()
        finally:
            await browser.close()


asyncio.run(main())
