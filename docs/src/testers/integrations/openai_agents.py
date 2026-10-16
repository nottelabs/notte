# @sniptest filename=notte_openai_agents.py
# @sniptest typecheck_only=true
import asyncio
import os

from agents import Agent, RunConfig, Runner
from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter
from notte_sdk import NotteClient
from pydantic import BaseModel


class Heading(BaseModel):
    heading: str


async def main() -> dict[str, str]:
    with NotteClient().Session() as session:
        async with MCPServerStreamableHttp(
            name="Notte",
            params={
                "url": os.environ.get("NOTTE_API_URL", "https://api.notte.cc").rstrip("/") + "/mcp",
                "headers": {"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
            },
            client_session_timeout_seconds=120,
            tool_filter=create_static_tool_filter(
                allowed_tool_names=["browser_action", "browser_observe", "browser_scrape"]
            ),
        ) as server:
            agent = Agent(
                name="Browser reader",
                model="gpt-4.1-mini",
                instructions=f"Use only browser_id {session.session_id}. Read the page with Notte tools.",
                mcp_servers=[server],
                output_type=Heading,
            )
            run = await Runner.run(
                agent,
                "Visit https://example.com and return its main heading.",
                max_turns=8,
                run_config=RunConfig(tracing_disabled=True),
            )
            heading = run.final_output_as(Heading).heading
            print(heading)
            return {"heading": heading, "session_id": session.session_id}


result = asyncio.run(main())
