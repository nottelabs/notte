import asyncio

from dotenv import load_dotenv
from notte_agent.falco.agent import (
    FalcoAgent as Agent,
)
from notte_agent.falco.agent import (
    FalcoAgentConfig as AgentConfig,
)

# Load environment variables
_ = load_dotenv()

if __name__ == "__main__":
    parser = AgentConfig.create_parser()
    _ = parser.add_argument("--task", type=str, required=True, help="The task to run the agent on.")
    args = parser.parse_args()

    # Create config with human-in-the-loop enabled
    config = AgentConfig.from_args(args).map_session(lambda session: session.agent_mode())

    agent = Agent(config=config)

    print("🤖 Starting agent with human-in-the-loop enabled")
    print("ℹ️  The agent will pause and wait for your input when a captcha is detected")
    print("ℹ️  Press Enter to continue after solving any captchas")
    print("-" * 80)

    out = asyncio.run(agent.run(args.task))
    print(out)

# Example usage:
# export task="open google flights and book cheapest flight from nyc to sf"
# uv run examples/human_in_the_loop.py --task $task --reasoning_model "openai/gpt-4o" --session.disable_web_security True
