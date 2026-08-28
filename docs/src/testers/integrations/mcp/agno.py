# @sniptest filename=notte_agno.py
# @sniptest typecheck_only=true
import asyncio
import os

from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.tools.mcp import MCPTools


async def main():
    # Notte authenticates with a bearer token, so use header_provider
    async with MCPTools(
        url="https://api.notte.cc/mcp/",
        transport="streamable-http",
        header_provider=lambda: {"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
    ) as notte_tools:
        print(f"Loaded {len(notte_tools.functions)} Notte tools")

        agent = Agent(model=Claude(id="claude-sonnet-4-5-20250929"), tools=[notte_tools])
        await agent.aprint_response("What is the H1 on https://example.com?")


asyncio.run(main())
