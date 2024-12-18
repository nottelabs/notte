import asyncio
from argparse import ArgumentParser

from dotenv import load_dotenv
from loguru import logger

from notte.common.parser import BaseNotteParser, Parser
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
    default="openai/gpt-4o",
)

parser.add_argument(
    "--headless",
    type=bool,
    default=False,
)

parser.add_argument(
    "--max-steps",
    type=int,
    default=10,
)


class Agent:
    """
    A base agent implementation that coordinates between an LLM and the Notte environment.

    This class demonstrates how to build an agent that can:
    1. Maintain a conversation with an LLM
    2. Execute actions in the Notte environment
    3. Parse and format responses between the LLM and Notte

    To customize this agent:
    1. Implement your own Parser class to format observations and actions
    2. Modify the conversation flow in the run() method
    3. Adjust the think() method to handle LLM interactions
    4. Customize the ask_notte() method for your specific needs

    Args:
        goal (str): The task description for the agent
        model (str): The LLM model identifier
        max_steps (int): Maximum number of steps before terminating
        headless (bool): Whether to run browser in headless mode
        parser (Parser | None): Custom parser for formatting interactions
    """

    def __init__(
        self,
        goal: str,
        model: str,
        max_steps: int,
        headless: bool,
        parser: Parser | None = None,
    ):
        self.goal: str = goal
        self.model: str = model
        self.llm: LLMEngine = LLMEngine()
        _ = load_dotenv()
        self.max_steps: int = max_steps
        self.headless: bool = headless
        # Users should implement their own parser to customize how observations
        # and actions are formatted for their specific LLM and use case
        self.parser: Parser = parser or BaseNotteParser()

    def think(self, messages: list[dict[str, str]]) -> str:
        """
        Processes the conversation history through the LLM to decide the next action.

        Override this method to customize how your agent interacts with the LLM,
        including prompt engineering and response processing.

        Args:
            messages: List of conversation messages in the format expected by your LLM

        Returns:
            str: The LLM's response indicating the next action
        """
        response = self.llm.completion(
            messages=messages,
            model=self.model,
        )
        return response.choices[0].message.content

    async def ask_notte(self, env: NotteEnv, text: str) -> str:
        """
        Executes actions in the Notte environment based on LLM decisions.

        This method demonstrates how to:
        1. Parse LLM output into Notte commands
        2. Execute those commands in the environment
        3. Format the results back into text for the LLM

        Users should customize this method to:
        - Handle additional Notte endpoints
        - Implement custom error handling
        - Format observations specifically for their LLM

        Args:
            env: The Notte environment instance
            text: The LLM's response containing the desired action

        Returns:
            str: Formatted observation from the environment
        """
        notte_endpoint = self.parser.which(text)
        logger.debug(f"Picking {notte_endpoint} endpoint")
        match notte_endpoint:
            case "observe":
                observe_params = self.parser.observe(text)
                obs = await env.observe(observe_params.url)
                return self.parser.textify(obs)
            case "step":
                step_params = self.parser.step(text)
                obs = await env.step(step_params.action_id, step_params.params)
                return self.parser.textify(obs)
            case _:
                logger.debug(f"Unknown provided endpoint: {notte_endpoint}")
                return self.parser.rules()

    def is_done(self, text: str) -> bool:
        return self.parser.is_done(text)

    async def run(self) -> None:
        """
        Main execution loop that coordinates between the LLM and Notte environment.

        This method shows a basic conversation flow. Consider customizing:
        1. The initial system prompt
        2. How observations are added to the conversation
        3. When and how to determine task completion
        4. Error handling and recovery strategies
        """
        logger.info("🚀 starting")
        # Notte is run in full mode, which means that both data extraction and action listing are enabled
        async with NotteEnv(headless=self.headless) as env:
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful web agent. Your goal is to " + self.goal,
                },
                {"role": "user", "content": await self.ask_notte(env, "")},
            ]

            for i in range(self.max_steps):
                logger.info(f"> step {i}: looping in")
                # Let the LLM Agent think about the next action
                resp: str = self.think(messages)
                messages.append({"role": "assistant", "content": resp})
                logger.info(f"🤖 {resp}")
                # Check if the task is done
                if self.is_done(resp):
                    done_answer = self.parser.get_done_answer(resp)
                    logger.info(f"😎 task completed with answer: {done_answer}")
                    return
                # Ask Notte to perform the selected action
                obs: str = await self.ask_notte(env, resp)
                messages.append({"role": "user", "content": obs})
                logger.info(f"🌌 {obs}")
            # If the task is not done, raise an error
            logger.info(f"👿 failed to solve task in {self.max_steps} steps")


if __name__ == "__main__":
    args = parser.parse_args()
    out = asyncio.run(
        Agent(
            goal=args.goal,
            model=args.model,
            max_steps=args.max_steps,
            headless=args.headless,
        ).run()
    )
