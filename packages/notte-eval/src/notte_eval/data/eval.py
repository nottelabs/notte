# flake8: noqa: E501
import base64
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, final

import chevron
from loguru import logger
from notte_agent.common.conversation import Conversation
from notte_agent.common.types import AgentResponse
from notte_core.common.config import LlmModel
from notte_core.llms.engine import LLMEngine
from typing_extensions import override

from notte_eval.data.load_data import BenchmarkTask


class BaseEvaluator(ABC):
    def __init__(
        self,
        api_model: str | None = None,
        max_retries: int = 5,
    ):
        self.api_model: str = api_model or LlmModel.default()
        self.llm: LLMEngine = LLMEngine(model=api_model)
        self.conv: Conversation = Conversation()
        if max_retries <= 0:
            raise ValueError("max_retries must be greater than 0")
        self.max_retries: int = max_retries

    async def _call_llm_evaluator(self) -> str:
        for _ in range(self.max_retries):
            try:
                logger.info("Calling LLM to get the auto evaluation......")
                retval = await self.llm.single_completion(self.conv.messages())
                if retval is None:
                    raise ValueError("LLM output should not be None")
                return retval
            except Exception as e:
                logger.error(e)
                if type(e).__name__ == "InvalidRequestError":
                    raise
                time.sleep(10 if type(e).__name__ != "APIError" else 15)
        raise Exception(f"Failed to get the auto evaluation after max retries={self.max_retries}")

    @abstractmethod
    async def evaluate_task(self, task: BenchmarkTask, output: AgentResponse) -> int | None:
        raise NotImplementedError


@final
class SimpleWebVoyagerEvaluator(BaseEvaluator):
    SYSTEM_PROMPT = """As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Reference Anwser: This is the reference answer provided by the evaluator. It serves as one possible answer to the task.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

-- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the reference anwser, evaluating whether the provided answer aligns with the reference anwser for the specific task.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- NOTE that the Reference Anwser is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between them.

You should elaborate on how you arrived at your final evaluation and then provide a definitive verdict on whether the task has been successfully accomplished, either as 'SUCCESS' or 'NOT SUCCESS'.

You should start by breaking down the Web Task Instruction into smaller sub-components and then evaluate each sub-component against the Reference Anwser and Result Response.
Then validate that whether or not each subtask has been completed to provide your final answer
"""

    USER_PROMPT = """
1. Web Task Instruction: {{task}}
2. Reference Anwser: {{ref_answer}}
3. Result Response: {{answer}}
"""

    @override
    async def evaluate_task(self, task: BenchmarkTask, output: AgentResponse) -> int | None:
        self.conv.reset()
        self.conv.add_system_message(content=self.SYSTEM_PROMPT)
        self.conv.add_user_message(
            content=chevron.render(
                self.USER_PROMPT,
                {"task": task.question, "ref_answer": task.answer, "answer": output.answer},
            )
        )
        response = await self._call_llm_evaluator()
        logger.info(response)

        # Determine evaluation result
        if "SUCCESS" not in response:
            return None
        return 0 if "NOT SUCCESS" in response else 1


@final
class WebVoyagerTrajectoryEvaluator(BaseEvaluator):
    SYSTEM_PROMPT = """As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Result Screenshots: This is a visual representation of the screen showing the result or intermediate state of performing a web task. It serves as visual proof of the actions taken in response to the instruction.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

-- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
-- You SHOULD NOT make assumptions based on information not presented in the screenshot when comparing it to the instructions.
-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshot and in the response, evaluating whether the actions taken align with the given instructions.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- NOTE that the screenshot is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between the text and the screenshots.
-- Note the difference: 1) Result response may contradict the screenshot, then the content of the screenshot prevails, 2) The content in the Result response is not mentioned on the screenshot, choose to believe the content.

You should elaborate on how you arrived at your final evaluation and then provide a definitive verdict on whether the task has been successfully accomplished, either as 'SUCCESS' or 'NOT SUCCESS'."""

    USER_PROMPT = """TASK: <task>
Result Response: <answer>
<num> screenshots at the end: """

    def __init__(
        self,
        api_key: str,
        max_attached_imgs: int = 3,
        api_model: str = "openai/gpt-4-vision-preview",
        process_dir: str = "results",
    ):
        super().__init__(api_model=api_model)
        self.api_key = api_key
        self.process_dir: Path = Path(process_dir)
        self.max_attached_imgs: int = max_attached_imgs

    def encode_image(self, image_name: str) -> str:
        with open(self.process_dir / image_name, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def get_image_content(self, image_name: str) -> bytes:
        with open(self.process_dir / image_name, "rb") as image_file:
            return image_file.read()

    def _get_screenshot_matches(self, res_files: list[Path]) -> list[bytes]:
        pattern_png = r"screenshot(\d+)\.png"
        matches: list[tuple[str, int]] = []
        for filename in res_files:
            str_filename = str(filename)
            match = re.search(pattern_png, str_filename)
            if match:
                matches.append((str_filename, int(match.group(1))))
        matches.sort(key=lambda x: x[1])
        path_matches = matches[-self.max_attached_imgs :]
        return [self.get_image_content(match[0]) for match in path_matches]

    @override
    async def evaluate_task(self, task: BenchmarkTask, output: AgentResponse) -> int | None:
        """Evaluate a WebVoyager task and return its success status.

        Args:
            process_dir: Directory containing the task data
            max_attached_imgs: Number of screenshots to analyze

        Returns:
            Optional[int]: 1 for success, 0 for failure, None if evaluation couldn't be determined
        """

        file_dir = self.process_dir / f"task{task.website_name}--{task.id}"
        if not file_dir.exists():
            raise ValueError(f"Directory {file_dir} does not exist")
        res_files = sorted(file_dir.glob("*"))

        # Load interaction messages
        with open(file_dir / "interact_messages.json") as fr:
            it_messages: list[Any] = json.load(fr)

        if len(it_messages) == 1:
            raise ValueError(f"Not find answer for {file_dir} only system messages")

        try:
            # Prepare messages for GPT-4V
            user_prompt = (
                self.USER_PROMPT.replace("<task>", task.question)
                .replace("<answer>", output.answer)
                .replace("<num>", str(self.max_attached_imgs))
            )
            self.conv.reset()
            self.conv.add_system_message(content=self.SYSTEM_PROMPT)

            contents: list[str | bytes] = [
                user_prompt,
                # Process screenshots
                *self._get_screenshot_matches(res_files),
                "Your verdict:\n",
            ]
            self.conv.add_user_messages(contents)

            # Get evaluation from GPT-4V
            response = await self._call_llm_evaluator()
            logger.info(response)

            # Determine evaluation result
            if "SUCCESS" not in response:
                return None
            return 0 if "NOT SUCCESS" in response else 1

        except Exception as e:
            logger.error(f"Error processing {self.process_dir}: {str(e)}")
            return None
