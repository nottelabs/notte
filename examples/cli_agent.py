import asyncio

from dotenv import load_dotenv
from notte_agent.falco.agent import (
    FalcoAgent as Agent,
)
from notte_agent.falco.agent import (
    FalcoAgentConfig as AgentConfig,
)

import notte

# Load environment variables
_ = load_dotenv()

if __name__ == "__main__":
    parser = AgentConfig.create_parser()
    _ = parser.add_argument("--task", type=str, required=True, help="The task to run the agent on.")
    args = parser.parse_args()
    config = AgentConfig.from_args(args).map_session(lambda session: session.agent_mode())

    async def run():
        async with notte.Session(config=config.session) as session:
            agent = Agent(config=config, window=session.window)

            return await agent.run(args.task)

    print(asyncio.run(run()))

# export task="open google flights and book cheapest flight from nyc to sf"
# uv run examples/cli_agent.py --task $task --reasoning_model "openai/gpt-4o" --session.disable_web_security True
