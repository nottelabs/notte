# @sniptest filename=async_scrape.py
import asyncio

from notte_sdk import AsyncNotteClient

urls = ["https://example.com", "https://www.notte.cc"]


async def main() -> None:
    async with AsyncNotteClient() as client:
        # each scrape starts and stops its own session. The TaskGroup runs them concurrently and
        # waits for every one, cleanup included, before the client closes.
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(client.scrape(url)) for url in urls]
        for url, task in zip(urls, tasks):
            print(url, task.result()[:100])


asyncio.run(main())
