# @sniptest filename=notte_openai_agents.py
# @sniptest typecheck_only=true
import asyncio
import os

from agents import Agent, OpenAIResponsesModel, RunConfig, Runner
from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter
from notte_sdk import NotteClient
from openai import AsyncOpenAI
from pydantic import BaseModel


class PageTitle(BaseModel):
    title: str


async def main() -> dict[str, str]:
    with NotteClient().Session(max_duration_minutes=3) as session:
        try:
            async with (
                AsyncOpenAI(timeout=120) as model_client,
                MCPServerStreamableHttp(
                    name="Notte",
                    params={
                        "url": (os.environ.get("NOTTE_API_URL") or "https://api.notte.cc").rstrip("/") + "/mcp",
                        "headers": {"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
                    },
                    client_session_timeout_seconds=120,
                    tool_filter=create_static_tool_filter(
                        allowed_tool_names=["browser_action", "browser_observe", "browser_scrape"]
                    ),
                ) as server,
            ):
                agent = Agent(
                    name="Browser reader",
                    model=OpenAIResponsesModel(
                        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), openai_client=model_client
                    ),
                    instructions=f"Use only browser_id {session.session_id}. Read the page with Notte tools.",
                    mcp_servers=[server],
                    output_type=PageTitle,
                )
                run = await Runner.run(
                    agent,
                    "Visit https://example.com and return its page title.",
                    max_turns=8,
                    run_config=RunConfig(tracing_disabled=True),
                )
                title = run.final_output_as(PageTitle).title
                print(title)
                return {"title": title, "session_id": session.session_id}
        except Exception:
            raise RuntimeError(f"OpenAI agent failed (session {session.session_id})") from None


with asyncio.Runner() as runner:
    result = runner.run(main())
