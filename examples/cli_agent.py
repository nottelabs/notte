import asyncio

from dotenv import load_dotenv

from notte_agents.falco.agent import (
    FalcoAgent as Agent,
)
from notte_agents.falco.agent import (
    FalcoAgentConfig as AgentConfig,
)

# Load environment variables
_ = load_dotenv()

if __name__ == "__main__":
    parser = AgentConfig.create_parser()
    _ = parser.add_argument("--task", type=str, required=True, help="The task to run the agent on.")
    args = parser.parse_args()
    config = AgentConfig.from_args(args).map_env(lambda env: env.disable_web_security().user_mode())
    agent = Agent(config=config)

    out = asyncio.run(agent.run(args.task))
    print(out)


# uvicorn examples.api:app --reload
# export task="Go to twitter.com and login with the account lucasgiordano@gmail.com and password mypassword8982"
# python run.py --task $task --reasoning_model "openai/gpt-4o"
