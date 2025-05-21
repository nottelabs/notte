import typer
from dotenv import load_dotenv
from notte_agent import Agent
from notte_agent.common.types import AgentResponse
from notte_core.llms.engine import LlmModel

# Load environment variables
_ = load_dotenv()


def main(headless: bool, task: str, reasoning_model: str) -> AgentResponse:
    agent = Agent(headless=headless, reasoning_model=LlmModel(reasoning_model))
    return agent.run(task)


if __name__ == "__main__":
    print(typer.run(main))

# export task="open google flights and book cheapest flight from nyc to sf"
# uv run examples/cli_agent.py --task $task --reasoning_model "openai/gpt-4o"
