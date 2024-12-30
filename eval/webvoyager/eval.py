# flake8: noqa: E501
import base64
import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, final

import chevron
from litellm import completion
from loguru import logger
from typing_extensions import override

from notte.common.agent import AgentOutput

from .load_data import WebVoyagerTask


class BaseWebVoyagerEvaluator(ABC):

    def __init__(
        self,
        # api_model: str = "openai/gpt-4-turbo",
        api_model: str = "groq/llama-3.3-70b-versatile",
    ):
        self.api_model: str = api_model

    def _call_llm_evaluator(self, messages: list[dict[str, Any]]) -> str:
        while True:
            try:
                logger.info("Calling LLM to get the auto evaluation......")
                response = completion(
                    model=self.api_model,
                    messages=messages,
                    max_tokens=1000,
                    seed=42,
                    temperature=0,
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(e)
                if isinstance(e, Exception) and type(e).__name__ == "InvalidRequestError":
                    raise
                time.sleep(10 if type(e).__name__ != "APIError" else 15)

    @abstractmethod
    def evaluate_task(self, task: WebVoyagerTask, output: AgentOutput) -> int | None:
        raise NotImplementedError


@final
class SimpleWebVoyageEvaluator(BaseWebVoyagerEvaluator):

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
    def evaluate_task(self, task: WebVoyagerTask, output: AgentOutput) -> int | None:

        response = self._call_llm_evaluator(
            [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": chevron.render(
                        self.USER_PROMPT,
                        {"task": task.question, "ref_answer": task.ref_answers[0].answer, "answer": output.answer},
                    ),
                },
            ]
        )
        logger.info(response)

        # Determine evaluation result
        if "SUCCESS" not in response:
            return None
        return 0 if "NOT SUCCESS" in response else 1


@final
class WebVoyagerTrajectoryEvaluator(BaseWebVoyagerEvaluator):
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
        self.api_key = api_key
        self.api_model = api_model
        self.process_dir: Path = Path(process_dir)
        self.max_attached_imgs: int = max_attached_imgs

    def encode_image(self, image_name: str) -> str:
        with open(self.process_dir / image_name, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _get_screenshot_matches(self, res_files: list[str]) -> list[tuple[str, int]]:
        pattern_png = r"screenshot(\d+)\.png"
        matches = []
        for filename in res_files:
            match = re.search(pattern_png, filename)
            if match:
                matches.append((filename, int(match.group(1))))
        matches.sort(key=lambda x: x[1])
        return matches[-self.max_attached_imgs :]

    def _prepare_image_content(self, screenshot_files: list[tuple[str, int]]) -> list[dict[str, Any]]:
        return [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{self.encode_image(png_file[0])}"}}
            for png_file in screenshot_files
        ]

    def evaluate_task(self, task: WebVoyagerTask, output: AgentOutput) -> int | None:
        """Evaluate a WebVoyager task and return its success status.

        Args:
            process_dir: Directory containing the task data
            max_attached_imgs: Number of screenshots to analyze

        Returns:
            Optional[int]: 1 for success, 0 for failure, None if evaluation couldn't be determined
        """

        file_dir = self.process_dir / f"task{task.name}--{task.id}"
        if not file_dir.exists():
            raise ValueError(f"Directory {file_dir} does not exist")
        res_files = sorted(file_dir.glob("*"))

        # Load interaction messages
        with open(file_dir / "interact_messages.json") as fr:
            it_messages: list[Any] = json.load(fr)

        if len(it_messages) == 1:
            raise ValueError(f"Not find answer for {file_dir} only system messages")

        try:
            # Process screenshots
            screenshot_matches = self._get_screenshot_matches(res_files)
            image_content = self._prepare_image_content(screenshot_matches)

            # Prepare messages for GPT-4V
            user_prompt = (
                self.USER_PROMPT.replace("<task>", task.question)
                .replace("<answer>", output.answer)
                .replace("<num>", str(self.max_attached_imgs))
            )

            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_prompt}]
                    + image_content
                    + [{"type": "text", "text": "Your verdict:\n"}],
                },
            ]

            # Get evaluation from GPT-4V
            response = self._call_llm_evaluator(messages)
            logger.info(response)

            # Determine evaluation result
            if "SUCCESS" not in response:
                return None
            return 0 if "NOT SUCCESS" in response else 1

        except Exception as e:
            logger.error(f"Error processing {self.process_dir}: {str(e)}")
            return None
