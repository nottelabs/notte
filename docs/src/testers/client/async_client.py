# @sniptest filename=async_client.py
import asyncio

from notte_sdk import AsyncNotteClient


async def main() -> None:
    # `async with` closes the client's connections on exit
    async with AsyncNotteClient() as client:
        await client.health_check()

    # without `async with`, close the client yourself
    client = AsyncNotteClient()
    try:
        await client.health_check()
    finally:
        await client.aclose()


asyncio.run(main())
