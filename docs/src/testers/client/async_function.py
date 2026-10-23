# @sniptest filename=async_function.py
import asyncio

from notte_sdk import AsyncNotteClient


async def main() -> None:
    async with AsyncNotteClient() as client:
        # creating a function sends a request, so await it
        function = await client.Function(path="my_function.py", name="Async example")
        try:
            # loading a function by ID sends no request until you use it
            same_function = client.Function(function_id=function.function_id)
            result = await same_function.run(url="https://example.com")
            print(result.status, result.result)
        finally:
            await function.delete()


asyncio.run(main())
