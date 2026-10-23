# @sniptest filename=async_scrape.py
import asyncio

from notte_sdk import AsyncNotteClient

urls = ["https://example.com", "https://www.notte.cc"]


async def main() -> None:
    async with AsyncNotteClient() as client:
        # each scrape starts and stops its own session; gather runs them concurrently
        pages = await asyncio.gather(*(client.scrape(url) for url in urls))
        for url, markdown in zip(urls, pages):
            print(url, markdown[:100])


asyncio.run(main())
