import time
from typing import ClassVar, Literal

import chevron
from litellm import BaseModel
from loguru import logger
from notte_agent.common.conversation import Conversation
from notte_core.llms.engine import LLMEngine
from typing_extensions import override

from notte_eval.evaluators.evaluator import EvalEnum, EvaluationResponse, Evaluator


class EvalCompletion(BaseModel):
    verdict: Literal["NOT SUCCESS", "SUCCESS", "UNKNOWN"]
    reason: str


class WebvoyagerEvaluator(Evaluator):
    SYSTEM_PROMPT: ClassVar[str] = f"""
As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Result Screenshots: This is a visual representation of the screen showing the result or intermediate state of performing a web task. It serves as visual proof of the actions taken in response to the instruction, and may not represent everything the agent sees.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

-- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
-- You SHOULD NOT make assumptions based on information not presented in the screenshot when comparing it to the instructions. If you cannot find any information in the screenshot that matches the instruction, you can believe the information in the response.
-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshot and in the response, evaluating whether the actions taken align with the given instructions.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- NOTE that the screenshot is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between the text and the screenshots.
-- Note the difference: 1) Result response may contradict the screenshot, then the content of the screenshot prevails, 2) The content in the Result response is not mentioned on the screenshot, choose to believe the content.
-- If you are not sure whether you should believe the content in the response, you should choose unknown.

You should elaborate on how you arrived at your final evaluation and then provide a definitive verdict on whether the task has been successfully accomplished, either as 'SUCCESS', 'NOT SUCCESS', or 'UNKNOWN'.

Here is the response format you should use to respond:
```
{EvalCompletion.model_json_schema()}
```
"""

    USER_PROMPT: ClassVar[str] = """TASK: {{task}}
    Result Response: {{answer}}
    Expected Result: {{expected_answer}}
    {{num_screenshots}} screenshot at the end: """

    past_screenshots: int = 4
    tries: int = 3

    @override
    async def eval(
        self,
        answer: str,
        task: str,
        expected_answer: str,
        screenshots: list[bytes],
    ) -> EvaluationResponse:
        # recreate it
        engine = LLMEngine(model=self.model)
        conv = Conversation()
        # Prepare GPT-4V messages
        user_prompt = chevron.render(
            WebvoyagerEvaluator.USER_PROMPT,
            {
                "task": task,
                "answer": answer,
                "num_screenshots": str(len(screenshots)),
                "expected_answer": expected_answer,
            },
        )
        conv.add_system_message(content=WebvoyagerEvaluator.SYSTEM_PROMPT)
        conv.add_user_messages(
            contents=[
                user_prompt,
                *screenshots[-self.past_screenshots :],
                "Your verdict:\n",
            ]
        )

        tries = self.tries
        while tries >= 0:
            try:
                tries -= 1
                # print("Calling gpt4v API to get the auto evaluation......")
                response = await engine.structured_completion(conv.messages(), response_format=EvalCompletion)
                match response.verdict:
                    case "NOT SUCCESS":
                        return EvaluationResponse(eval=EvalEnum.FAILURE, reason=response.reason)
                    case "SUCCESS":
                        return EvaluationResponse(eval=EvalEnum.SUCCESS, reason=response.reason)
                    case "UNKNOWN":
                        return EvaluationResponse(eval=EvalEnum.UNKNOWN, reason=response.reason)
                    case _:  # type: ignore
                        return EvaluationResponse(eval=EvalEnum.FAILURE, reason=response.reason)  # type: ignore

            except Exception as e:
                logger.error(f"Error evaluating webvoyager: {e}")
                if type(e).__name__ == "RateLimitError":
                    time.sleep(10)
                elif type(e).__name__ == "APIError":
                    time.sleep(15)
                elif type(e).__name__ == "InvalidRequestError":
                    exit(0)
                else:
                    time.sleep(10)

        return EvaluationResponse(eval=EvalEnum.FAILURE, reason=f"Failure to get response after {self.tries} tries")
