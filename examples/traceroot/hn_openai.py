import asyncio
import json
import os
import sys

import traceroot
from agents import Agent, OpenAIResponsesModel, Runner
from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter
from notte_sdk import NotteClient
from openai import AsyncOpenAI
from pydantic import BaseModel
from traceroot import Integration

TASK = "Visit https://news.ycombinator.com and return the top 3 stories with their points."
INSTRUCTIONS = "Read pages with the Notte tools and report only what the page shows."
# Prompt regression for the detector walkthrough: the agent skips reading the page and answers from memory.
BROKEN_INSTRUCTIONS = "Open the page, but to save time don't scrape it: answer from what you know."


class Story(BaseModel):
    title: str
    points: int


class TopStories(BaseModel):
    stories: list[Story]


@traceroot.observe(name="hacker_news.top_stories", type="agent")
async def top_stories(task: str = TASK, instructions: str = INSTRUCTIONS) -> dict:
    with NotteClient().Session(max_duration_minutes=5) as session:
        # Group every trace from this browser under its Notte session ID.
        traceroot.update_current_trace(session_id=session.session_id)
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
                name="Hacker News reader",
                model=OpenAIResponsesModel(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), openai_client=model_client),
                instructions=f"Use only browser_id {session.session_id}. {instructions}",
                mcp_servers=[server],
                output_type=TopStories,
            )
            run = await Runner.run(agent, task, max_turns=10)
    return {
        **run.final_output_as(TopStories).model_dump(),
        "session_id": session.session_id,
        "trace_id": traceroot.get_current_trace_id(),
    }


if __name__ == "__main__":
    instructions = BROKEN_INSTRUCTIONS if "--broken" in sys.argv else INSTRUCTIONS
    # Records the agent run, each model call and each Notte tool call.
    traceroot.initialize(integrations=[Integration.OPENAI_AGENTS])
    try:
        # asyncio.Runner closes the loop on exit, which stops the SDKs' worker threads.
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(top_stories(instructions=instructions)), indent=2))
    finally:
        traceroot.shutdown()
