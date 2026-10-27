import asyncio

from notte_sdk import AsyncNotteClient


async def main():
    async with AsyncNotteClient() as client:
        async with client.Session() as session:
            page = await session.page
            await page.goto("https://example.com")
            title = await page.title()
            print(f"Title: {title}")
            await page.screenshot(path="screenshot.png")


asyncio.run(main())
