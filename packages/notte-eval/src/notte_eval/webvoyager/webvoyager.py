import time
from typing import ClassVar

from notte_agent.common.conversation import Conversation
from notte_core.llms.engine import LLMEngine
from pydantic import BaseModel
from typing_extensions import override

from notte_eval.webvoyager.evaluator import EvalEnum, EvaluationResponse, Evaluator


class EvalCompletion(BaseModel):
    verdict: str
    reason: str


class WebvoyagerEvaluator(Evaluator):
    SYSTEM_PROMPT: ClassVar[
        str
    ] = """As an evaluator, you will be presented with three primary components to assist you in your role:

    1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

    2. Result Screenshots: This is a visual representation of the screen showing the result or intermediate state of performing a web task. It serves as visual proof of the actions taken in response to the instruction, and may not represent everything the agent sees.

    3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

    4. Expected Result: This is a textual expected response to help you determine if the execution was successful. It is possible that the expected result is out of date. Use your best judgement with the expected result and result screenshot to determine success to complete the assigned task.

    -- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
    -- You SHOULD NOT make assumptions based on information not presented in the screenshot when comparing it to the instructions. If you cannot find any information in the screenshot that matches the instruction, you can believe the information in the response.
    -- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshot and in the response, evaluating whether the actions taken align with the given instructions.
    -- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
    -- NOTE that the screenshot is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between the text and the screenshots.
    -- Note the difference: 1) Result response may contradict the screenshot, then the content of the screenshot prevails, 2) The content in the Result response is not mentioned on the screenshot, choose to believe the content.
    -- If you are not sure whether you should believe the content in the response, you should choose unknown.

    You should elaborate on how you arrived at your final evaluation and then provide a definitive verdict on whether the task has been successfully accomplished, either as 'SUCCESS', 'NOT SUCCESS', or 'UNKNOWN'.
    Respond in a JSON format with a field called "verdict" which should only be either 'SUCCESS', 'NOT SUCCESS', or 'UNKNOWN', and another field "reason" which should contain your how you arrived at your final evaluation.
    An example response might look like: {"verdict": "NOT SUCCESS", "reason": "The response didn't accomplish all the steps in the task."}"""

    USER_PROMPT: ClassVar[str] = """TASK: <task>
    Result Response: <answer>
    Expected Result: <expected>
    <num> screenshot at the end: """

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
        engine = LLMEngine(model=self.model)

        conv = Conversation()
        conv.add_system_message(content=WebvoyagerEvaluator.SYSTEM_PROMPT)

        # Prepare messages
        user_prompt_tmp = WebvoyagerEvaluator.USER_PROMPT.replace("<task>", task)
        user_prompt_tmp = user_prompt_tmp.replace("<answer>", answer)
        user_prompt_tmp = user_prompt_tmp.replace("<expected>", expected_answer)

        n_screenshots = 1

        if len(screenshots) == 0:
            n_screenshots = 0
            user_prompt_tmp = user_prompt_tmp.replace("<num>", str(n_screenshots))

            conv.add_user_message(
                content=user_prompt_tmp,
            )
        else:
            last_screenshot = screenshots[-1]
            user_prompt_tmp = user_prompt_tmp.replace("<num>", str(n_screenshots))

            conv.add_user_message(
                content=user_prompt_tmp,
                image=(last_screenshot),
            )

        res = "Failed to get response"
        verd = ""
        tries = self.tries
        while tries >= 0:
            try:
                tries -= 1
                # print("Calling gpt4v API to get the auto evaluation......")
                response = await engine.structured_completion(conv.messages(), EvalCompletion)
                res = str(response.reason)
                verd = str(response.verdict)
                break
            except Exception as e:
                print(e)
                if type(e).__name__ == "RateLimitError":
                    time.sleep(10)
                elif type(e).__name__ == "APIError":
                    time.sleep(15)
                elif type(e).__name__ == "InvalidRequestError":
                    exit(0)
                else:
                    time.sleep(10)

        if "NOT SUCCESS" in verd:
            auto_eval_res = EvalEnum.FAILURE
        elif "SUCCESS" in verd:
            auto_eval_res = EvalEnum.SUCCESS
        elif "UNKNOWN" in verd:
            auto_eval_res = EvalEnum.UNKNOWN
        else:
            auto_eval_res = EvalEnum.EVAL_FAIL

        return EvaluationResponse(eval=auto_eval_res, reason=res)
