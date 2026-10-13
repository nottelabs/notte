# @sniptest filename=notte_langchain.py
# @sniptest typecheck_only=true
import asyncio
import os

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent


async def main():
    client = MultiServerMCPClient(
        {
            "notte": {
                "url": "https://api.notte.cc/mcp/",
                "transport": "streamable_http",
                "headers": {"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
            }
        }
    )

    tools = await client.get_tools()
    print(f"Loaded {len(tools)} Notte tools")

    agent = create_react_agent("anthropic:claude-sonnet-4-5-20250929", tools)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": "What is the H1 on https://example.com?"}]})
    print(result["messages"][-1].content)


asyncio.run(main())
