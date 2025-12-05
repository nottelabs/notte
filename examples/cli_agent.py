from typing import Annotated

import typer
from dotenv import load_dotenv
from notte_agent.common.types import AgentResponse
from notte_core.common.config import LlmModel

import notte


def main(
    task: Annotated[str, typer.Option(..., help="Task to perform")],
    reasoning_model: Annotated[str, typer.Option(help="Reasoning model to use")] = LlmModel.default(),  # type: ignore[reportArgumentType]
    open_viewer: Annotated[bool, typer.Option(help="Open live viewer")] = False,
) -> AgentResponse:
    with notte.Session(open_viewer=open_viewer) as session:
        agent = notte.Agent(reasoning_model=reasoning_model, session=session)
        return agent.run(task=task)


if __name__ == "__main__":
    # Load environment variables
    env = load_dotenv()
    print(typer.run(main))

# uv run examples/cli_agent.py --task "go to notte.cc and extract the pricing information" --reasoning_model "openai/gpt-4o"
