# @sniptest filename=stagehand_complete.py
import asyncio
import os

from dotenv import load_dotenv
from notte_sdk import NotteClient
from stagehand import Stagehand

load_dotenv()


async def main():
    client = NotteClient()

    with client.Session() as session:
        stagehand = Stagehand(
            env="LOCAL",
            local_browser_launch_options={
                "cdp_url": session.cdp_url(),
            },
            model_name="openai/gpt-4.1",
            model_api_key=os.environ.get("MODEL_API_KEY"),
            verbose=1,
        )
        await stagehand.init()

        try:
            # Navigate to a webpage
            page = stagehand.page
            await page.goto("https://news.ycombinator.com")

            # Observe: find possible actions on the page
            observations = await stagehand.observe("find the top story link")
            print(f"Found {len(observations)} possible actions")

            # Act: click on the first result
            if observations:
                await stagehand.act(observations[0])

            # Extract: get structured data from the page
            result = await stagehand.extract(
                "extract the title and URL of this story",
                {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                    },
                },
            )
            print(f"Extracted: {result}")

        finally:
            await stagehand.close()

    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
