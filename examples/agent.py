import asyncio
from argparse import ArgumentParser

from dotenv import load_dotenv
from loguru import logger
from typing_extensions import override

from notte.common.agent import AgentOutput, BaseAgent
from notte.common.proxy import NotteProxy
from notte.env import NotteEnv
from notte.llms.engine import LLMEngine

_ = load_dotenv()

parser: ArgumentParser = ArgumentParser()
_ = parser.add_argument(
    "--task",
    type=str,
    required=True,
)
_ = parser.add_argument(
    "--model",
    type=str,
    default="openai/gpt-4o",
)

_ = parser.add_argument(
    "--headless",
    type=bool,
    default=False,
)

_ = parser.add_argument(
    "--max-steps",
    type=int,
    default=10,
)


class SimpleNotteAgent(BaseAgent):
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
        task (str): The task description for the agent
        model (str): The LLM model identifier
        max_steps (int): Maximum number of steps before terminating
        headless (bool): Whether to run browser in headless mode
        parser (Parser | None): Custom parser for formatting interactions
    """

    def __init__(
        self,
        model: str,
        max_steps: int,
        headless: bool,
        proxy: NotteProxy | None = None,
    ):
        self.model: str = model
        self.llm: LLMEngine = LLMEngine()
        self.max_steps: int = max_steps
        # Users should implement their own parser to customize how observations
        # and actions are formatted for their specific LLM and use case
        self.proxy: NotteProxy = NotteProxy()
        self.env: NotteEnv = NotteEnv(
            headless=headless,
            max_steps=max_steps,
        )

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

    async def reset(self):
        await self.env.reset()
        self.step_count = 0

    @override
    async def run(self, task: str, url: str | None = None) -> AgentOutput:
        """
        Main execution loop that coordinates between the LLM and Notte environment.

        This method shows a basic conversation flow. Consider customizing:
        1. The initial system prompt
        2. How observations are added to the conversation
        3. When and how to determine task completion
        4. Error handling and recovery strategies
        """
        logger.info(f"🚀 starting agent with task: {task} and url: {url}")
        async with self.env:
            messages = [
                {
                    "role": "system",
                    "content": f"""You are a helpful web agent.
Now you are given the task: {task}.
Please interact with : {url or 'the web'} to get the answer.

Instructions:
- At every step, you will be provided with a list of actions you can take.
- If you are asked to accept cookies to continue, please accept them. Accepting cookies is MANDATORY.
- If you see one action about cookie management, you should stop thinking about the goal and accept cookies DIRECTLY.
- If you are asked to signin / signup to continue browsing, abort the task and explain why you can't proceed.
""",
                },
                {
                    "role": "user",
                    "content": await self.ask_notte(""),
                },
            ]

            for i in range(self.max_steps):
                logger.info(f"> step {i}: looping in")
                # Let the LLM Agent think about the next action
                resp: str = self.think(messages)
                messages.append({"role": "assistant", "content": resp})
                logger.info(f"🤖 {resp}")
                # Ask Notte to perform the selected action
                obs, output = await self.ask_notte(resp)
                # Check if the task is done
                if output is not None:
                    status = "😎 task completed sucessfully" if output.success else "👿 task failed"
                    logger.info(f"{status} with answer: {output.answer}")
                    return AgentOutput(
                        answer=output.answer,
                        success=output.success,
                        snapshot=self.env.context.snapshot,
                        messages=messages,
                    )

                messages.append({"role": "user", "content": obs})
                logger.info(f"🌌 {obs}")
            # If the task is not done, raise an error
            error_msg = f"Failed to solve task in {self.max_steps} steps"
            logger.info(f"🚨 {error_msg}")
            return AgentOutput(
                answer=error_msg,
                success=False,
                snapshot=self.env.context.snapshot,
                messages=messages,
            )


if __name__ == "__main__":
    args = parser.parse_args()
    agent = SimpleNotteAgent(
        model=args.model,
        max_steps=args.max_steps,
        headless=args.headless,
    )
    out = asyncio.run(agent.run(args.task))
    print(out)
