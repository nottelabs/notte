from typing import Annotated

import typer
from dotenv import load_dotenv
from notte_agent import Agent
from notte_agent.common.types import AgentResponse
from notte_core.common.config import LlmModel


def main(
    task: Annotated[str, typer.Option(..., help="Task to perform")],
    reasoning_model: Annotated[str, typer.Option(help="Reasoning model to use")] = LlmModel.default(),  # type: ignore[reportArgumentType]
    headless: Annotated[bool, typer.Option(help="Run in headless mode")] = False,
) -> AgentResponse:
    agent = Agent(headless=headless, reasoning_model=LlmModel(reasoning_model))
    return agent.run(task=task)


if __name__ == "__main__":
    # Load environment variables
    env = load_dotenv()
    print(typer.run(main))

# uv run examples/cli_agent.py --task "go to notte.cc and extract the pricing information" --reasoning_model "openai/gpt-4o"
