# @sniptest filename=notte_stagehand.py
# @sniptest show=22-37
# @sniptest typecheck_only=true
import asyncio
import os
from typing import Any

from notte_sdk import NotteClient


class LocalBrowser:
    async def connect(self, *, cdp_url: str) -> Any: ...


local_browser = LocalBrowser()


class Stagehand:
    def __init__(self, *, browser: Any, model: str, api_key: str | None) -> None: ...
    async def initialize(self) -> None: ...
    async def extract(self, instruction: str) -> Any: ...
    async def close(self) -> None: ...


async def main():
    client = NotteClient()

    with client.Session() as session:
        # Stagehand attaches to the Notte browser over CDP
        stagehand = Stagehand(
            browser=await local_browser.connect(cdp_url=session.cdp_url()),
            model="anthropic/claude-sonnet-4-5-20250929",
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
        await stagehand.initialize()
        print(await stagehand.extract("the title of the top story"))
        await stagehand.close()


asyncio.run(main())
