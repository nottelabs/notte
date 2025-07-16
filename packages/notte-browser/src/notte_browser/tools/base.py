import datetime as dt
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Annotated, Any, Callable, TypeVar, Unpack, final

import markdownify  # type: ignore[import]
from loguru import logger
from notte_core.actions import EmailReadAction, ToolAction
from notte_core.browser.observation import StepResult
from notte_core.data.space import DataSpace
from notte_sdk.endpoints.personas import Persona
from notte_sdk.types import EmailResponse
from pydantic import BaseModel, Field
from typing_extensions import override

TToolAction = TypeVar("TToolAction", bound=ToolAction, contravariant=True)

ToolInputs = tuple[TToolAction]
# ToolInputs = tuple[TToolAction, BrowserWindow, BrowserSnapshot]

ToolExecutionFunc = Callable[[Any, Unpack[ToolInputs[TToolAction]]], StepResult]
ToolExecutionFuncSelf = Callable[[Unpack[ToolInputs[TToolAction]]], StepResult]


class BaseTool(ABC):
    _tools: dict[type[ToolAction], ToolExecutionFunc[ToolAction]] = {}  # type: ignore

    @abstractmethod
    def instructions(self) -> str:
        pass

    @classmethod
    def register(
        cls, action: type[TToolAction]
    ) -> Callable[[ToolExecutionFunc[TToolAction]], ToolExecutionFunc[TToolAction]]:
        def decorator(func: ToolExecutionFunc[TToolAction]) -> ToolExecutionFunc[TToolAction]:
            cls._tools[action] = func  # type: ignore
            return func  # type: ignore

        return decorator  # type: ignore

    def tools(self) -> dict[type[ToolAction], ToolExecutionFuncSelf[ToolAction]]:
        return {
            action: self.get_tool(action)  # type: ignore
            for action in self._tools.keys()
        }

    def get_action_map(self) -> dict[str, type[ToolAction]]:
        return {action.name(): action for action in self._tools.keys()}

    def get_tool(self, action: type[TToolAction]) -> ToolExecutionFuncSelf[TToolAction] | None:
        func = self._tools.get(action)
        if func is None:
            return None

        def wrapper(*args: Unpack[ToolInputs[TToolAction]]) -> StepResult:
            return func(self, *args)

        return wrapper

    def execute(self, *inputs: Unpack[ToolInputs[TToolAction]]) -> StepResult:
        (action,) = inputs
        tool_func = self.get_tool(type(action))
        if tool_func is None:
            raise ValueError(f"No tool found for action {type(action)}")
        return tool_func(*inputs)


class SimpleEmailResponse(BaseModel):
    subject: Annotated[str, Field(description="The subject of the email")]
    content: Annotated[str, Field(description="The body of the email")]
    created_at: Annotated[dt.datetime, Field(description="The date and time the email was sent")]
    sender_email: Annotated[str, Field(description="The email address of the sender")]


class ListEmailResponse(BaseModel):
    emails: list[SimpleEmailResponse]


# #########################################################
# #################### PERSONA TOOLS ######################
# #########################################################


@final
class PersonaTool(BaseTool):
    def __init__(self, persona: Persona, nb_retries: int = 3):
        super().__init__()
        self.persona = persona
        self.nb_retries = nb_retries

    @override
    def instructions(self) -> str:
        return f"""
PERSONAL INFORMATION MODULE
===========================

You have access to the following personal information
- First Name: {self.persona.info.first_name}
- Last Name: {self.persona.info.last_name}
- Email: {self.persona.info.email}
- Phone number: {self.persona.info.phone_number or "N/A"}

This is usefull if you need to fill forms that require personal information.

EMAIL HANDLING MODULE
=====================

Some websites require you to read emails to retrieve sign-in codes/links, 2FA codes or simply to check the inbox.
Use the {EmailReadAction.name()} action to read emails from the inbox.
"""

    @BaseTool.register(EmailReadAction)
    def read_emails(self, action: EmailReadAction) -> StepResult:
        raw_emails: Sequence[EmailResponse] = []
        time_str = f"in the last {action.timedelta}" if action.timedelta is not None else ""
        for _ in range(self.nb_retries):
            raw_emails = self.persona.emails(
                only_unread=action.only_unread,
                timedelta=action.timedelta,
                limit=action.limit,
            )
            if len(raw_emails) > 0:
                break
            # if we have not found any emails, we wait for 5 seconds and retry
            logger.warning(
                f"No emails found in the inbox {time_str}, waiting for 5 seconds and retrying {self.nb_retries} times"
            )
            time.sleep(5)

        if len(raw_emails) == 0:
            return StepResult(
                success=True,
                message=f"No emails found in the inbox {time_str}",
                data=DataSpace.from_structured(ListEmailResponse(emails=[])),
            )
        emails: list[SimpleEmailResponse] = []
        for email in raw_emails:
            content: str | None = email.text_content
            if content is None or len(content) == 0:
                content = markdownify.markdownify(email.html_content)  # type: ignore[attr-defined]
            emails.append(
                SimpleEmailResponse(
                    subject=email.subject,
                    content=content or "no content",  # type: ignore[attr-defined]
                    created_at=email.created_at,
                    sender_email=email.sender_email or "unknown",
                )
            )
        return StepResult(
            success=True,
            message=f"Successfully read {len(emails)} emails from the inbox {time_str}",
            data=DataSpace.from_structured(ListEmailResponse(emails=emails)),
        )
