from notte_agent.common.conversation import Conversation
from patchright.async_api import Locator
from pydantic import BaseModel

from notte_core.llms.engine import LLMEngine


class ActionVerifier:
    class NodeElements(BaseModel):
        outer_html: str
        tag_name: str
        attributes: str
        screenshot: bytes

    class Response(BaseModel):
        reason: str
        valid: bool

    def __init__(self, model: str, use_vision: bool) -> None:
        self.engine: LLMEngine = LLMEngine(model=model)
        self.use_vision: bool = use_vision

    async def extract_information(self, locator: Locator) -> NodeElements:
        outer_html = await locator.evaluate("el => el.outerHTML")
        tag_name = await locator.evaluate("el => el.tagName")
        attributes = await locator.evaluate(
            "el => { const attrs = {}; for (let i = 0; i < el.attributes.length; i++) { attrs[el.attributes[i].name] = el.attributes[i].value; } return attrs; }"
        )
        attributes_string = ", ".join(f"{k}={v}" for k, v in attributes.items())  # Format for LLM prompt
        screenshot = await locator.screenshot()
        return ActionVerifier.NodeElements(
            outer_html=outer_html, tag_name=tag_name, attributes=attributes_string, screenshot=screenshot
        )

    async def verify_locator(self, task: str, locator: Locator) -> Response:
        conv = Conversation()
        conv.add_system_message(self.system_prompt())

        extracted = await self.extract_information(locator)

        import logging

        logging.warning(f"{task=} {locator=}")

        user_message = f"""The task is: {task}. The element is a[n] {extracted.tag_name} with attributes {extracted.attributes}. The outer html is: {extracted.outer_html}.
        Is it suitable to perform the task?
        """
        conv.add_user_message(user_message, image=extracted.screenshot if self.use_vision else None)
        retval = self.engine.structured_completion(conv.messages(), ActionVerifier.Response)

        logging.warning(f"{retval=}")
        return retval

    def system_prompt(self) -> str:
        # Prepare the LLM prompt
        return """
        You are an expert in web automation. Your job is to help an llm agent decide if a webpage element does the correct job for a given task.
        You will be provided information about a webpage element: for example, a button that says "submit", and a task, for example: "submit the form".
        In the example of the button, since it mentions submit, while the task requires to submit the form, we expect the button to fulfill the correct task.

        You will be provided with information such as the OuterHTML for the element.
        CRITICAL: your output has to follow this json schema:

        ```
        {"reason": str, "valid": bool}
        ```

        For example:
        ```
        {"reason": "The button has text that mentions submitting the form, and the task is to submit the form", "valid": true}
        ```
        """
