# @sniptest filename=stagehand_basic.py
import asyncio
import os

from notte_sdk import NotteClient
from stagehand import Stagehand


async def main():
    client = NotteClient()

    with client.Session() as session:
        # Connect Stagehand to Notte's cloud browser via CDP
        stagehand = Stagehand(
            env="LOCAL",
            local_browser_launch_options={
                "cdp_url": session.cdp_url(),
            },
            model_name="openai/gpt-4.1",
            model_api_key=os.environ.get("MODEL_API_KEY"),
        )
        await stagehand.init()

        page = stagehand.page
        await page.goto("https://example.com")
        await stagehand.act("Click on the 'More information...' link")

        await stagehand.close()


asyncio.run(main())
