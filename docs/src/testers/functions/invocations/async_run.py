# @sniptest filename=async_run.py
import asyncio

from notte_sdk import NotteClient


async def main():
    function = NotteClient().Function("function_abc123")
    created = await asyncio.to_thread(function.create_run)
    pending = asyncio.create_task(
        asyncio.to_thread(
            function.run,
            function_run_id=created.function_run_id,
            url="https://example.com",
        )
    )

    # Other async work can run while execution is in progress.
    print(f"Run ID: {created.function_run_id}")
    result = await pending
    print(result.result)


asyncio.run(main())
