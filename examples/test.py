import asyncio
import os

from dotenv import load_dotenv

from notte.agents.falco.agent import FalcoAgent as Agent
from notte.agents.falco.agent import FalcoAgentConfig as AgentConfig


async def main():
    _ = load_dotenv()


    config = (
        AgentConfig()
    )
    agent = Agent(config=config)

    output = await agent.run(
        task = "Search for the latest news title about the NBA team the Los Angeles Lakers.",
        url = "https://www.google.com/"
    )
    print(output)


if __name__ == "__main__":
    # Run the async function
    asyncio.run(main())
