import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager

from deepagents import create_deep_agent
from deepagents.middleware.filesystem import FilesystemMiddleware
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import StructuredTool
from notte_sdk import NotteClient


def browser_tools(tools, session_id):
    names = {"browser_action", "browser_observe", "browser_scrape"}
    selected = [tool for tool in tools if tool.name in names]
    if {tool.name for tool in selected} != names:
        raise RuntimeError("Required browser tools are unavailable")

    def bind(tool):
        async def invoke(**args):
            return await tool.ainvoke({**args, "browser_id": session_id})

        return StructuredTool.from_function(
            coroutine=invoke, name=tool.name, description=tool.description, args_schema=tool.args_schema
        )

    return [bind(tool) for tool in selected]


@asynccontextmanager
async def mcp_connection(transport):
    adapter = MCPAdapter(transport)
    await adapter.__aenter__()
    try:
        yield adapter
    finally:
        failure = sys.exc_info()
        try:
            async with asyncio.timeout(5):
                await adapter.__aexit__(*failure)
        except Exception:
            if failure[0] is None:
                raise RuntimeError("MCP cleanup failed") from None


async def run(task: str) -> dict[str, str]:
    transport = StreamableHttpTransport(
        os.getenv("NOTTE_API_URL", "https://api.notte.cc").rstrip("/") + "/mcp/",
        headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
    )
    with NotteClient().Session(max_duration_minutes=3) as session:
        stage = "MCP connection"
        try:
            async with mcp_connection(transport) as adapter:
                stage = "tool discovery"
                tools = browser_tools(await adapter.list_tools(), session.session_id)
                stage = "agent initialization"
                agent = create_deep_agent(
                    model=ChatAnthropic(
                        model=os.getenv("DEEPAGENTS_MODEL", "claude-haiku-5-5"),
                        max_tokens=1024,
                        max_retries=0,
                        timeout=60,
                    ),
                    tools=tools,
                    middleware=[FilesystemMiddleware(tools=["read_file"])],
                    system_prompt=(
                        f"Use Notte browser tools with browser_id {session.session_id} for every browser call. "
                        "Navigate with browser_action before reading. Report only what the browser shows."
                    ),
                )
                stage = "agent execution"
                result = await agent.ainvoke({"messages": [{"role": "user", "content": task}]}, {"recursion_limit": 20})
                return {"answer": result["messages"][-1].text, "session_id": session.session_id}
        except Exception as error:
            code = getattr(error, "status_code", None)
            status = f" HTTP {code}" if type(code) is int else ""
            raise RuntimeError(
                f"Deep Agents failed during {stage}: {type(error).__name__}{status} (session {session.session_id})"
            ) from None


if __name__ == "__main__":
    print(
        json.dumps(asyncio.run(run(" ".join(sys.argv[1:]) or "Visit https://example.com and report its page title.")))
    )
