import asyncio
from argparse import ArgumentParser

from dotenv import load_dotenv
from loguru import logger
from notte.env import NotteEnv
from notte.llms.engine import LLMEngine

parser: ArgumentParser = ArgumentParser()
parser.add_argument(
    "--goal",
    type=str,
    required=True,
)
parser.add_argument(
    "--model",
    type=str,
    default="anthropic/claude-3-5-sonnet-20240620",
)
args = parser.parse_args()


class Agent:
    def __init__(self, goal: str):
        self.goal: str = goal
        self.llm: LLMEngine = LLMEngine()
        _ = load_dotenv()

    def think(self, messages: list[dict[str, str]]) -> str:
        response = self.llm.completion(
            messages=messages,
            model=args.model,
        )
        return response.choices[0].message.content

    async def run(self) -> None:
        logger.info("🚀 starting")
        async with NotteEnv() as env:
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful web agent. Your goal is to " + self.goal,
                },
                {"role": "user", "content": await env.chat("")},
            ]

            while True:
                resp: str = self.think(messages)
                messages.append({"role": "assistant", "content": resp})
                logger.info(f"🤖 {resp}")
                if "<done/>" in resp:
                    break
                obs: str = await env.chat(resp)
                messages.append({"role": "user", "content": obs})
                logger.info(f"🌌 {obs}")

            logger.info("😎 complete")


if __name__ == "__main__":
    out = asyncio.run(Agent(goal=args.goal).run())
