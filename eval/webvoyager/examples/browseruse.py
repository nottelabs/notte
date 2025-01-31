import asyncio
import json
import os
import random

from browser_use import Agent as BrowserUseAgent
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from eval.patcher import AgentPatcher
from eval.webvoyager.load_data import load_webvoyager_data

_ = load_dotenv()


async def main():
    tasks = load_webvoyager_data()

    task = random.choice(tasks)
    prompt = f"""You are a helpful web agent.
    Now you are given the task: {task.question}.
    Please interact with : {task.url or "the web"} to get the answer.
    """

    agent = BrowserUseAgent(
        task=prompt,
        llm=ChatOpenAI(model="gpt-4o"),
    )

    patcher = AgentPatcher()
    _ = patcher.log_io(agent.llm, ["invoke", "ainvoke"])
    _ = patcher.log_timings(agent, ["step", "run"])

    result = await agent.run(max_steps=20)
    results = {
        "output": result.model_dump(),
        "input_tokens": patcher.input_data,
        "output_tokens": patcher.output_data,
        "timing": patcher.timing_data,
    }

    with open(os.path.join("example_output.json"), "w") as f:
        _ = f.write(json.dumps(results))


if __name__ == "__main__":
    asyncio.run(main())
