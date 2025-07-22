import datetime as dt
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Callable, TypeVar, Unpack, final

import markdownify  # type: ignore[import]
from loguru import logger
from notte_core.actions import EmailReadAction, SmsReadAction, ToolAction
from notte_core.browser.observation import ExecutionResult
from notte_core.data.space import DataSpace
from notte_sdk.endpoints.personas import Persona
from notte_sdk.types import EmailResponse, SMSResponse
from pydantic import BaseModel, Field
from typing_extensions import override

TToolAction = TypeVar("TToolAction", bound=ToolAction, covariant=True)

ToolInputs = tuple[TToolAction]
# ToolInputs = tuple[TToolAction, BrowserWindow, BrowserSnapshot]

ToolExecutionFunc = Callable[[Any, Unpack[ToolInputs[TToolAction]]], ExecutionResult]
ToolExecutionFuncSelf = Callable[[Unpack[ToolInputs[TToolAction]]], ExecutionResult]


class BaseTool(ABC):
    _tools: Mapping[type[ToolAction], ToolExecutionFunc[ToolAction]] = {}  # type: ignore

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

    def tools(self) -> Mapping[type[ToolAction], ToolExecutionFuncSelf[ToolAction]]:
        return {
            action: self.get_tool(action)  # type: ignore
            for action in self._tools.keys()
        }

    def get_action_map(self) -> Mapping[str, type[ToolAction]]:
        return {action.name(): action for action in self._tools.keys()}

    def get_tool(self, action: type[TToolAction]) -> ToolExecutionFuncSelf[TToolAction] | None:
        func = self._tools.get(action)
        if func is None:
            return None

        def wrapper(*args: Unpack[ToolInputs[TToolAction]]) -> ExecutionResult:
            return func(self, *args)

        return wrapper

    def execute(self, *inputs: Unpack[ToolInputs[TToolAction]]) -> ExecutionResult:
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

    @staticmethod
    def from_email(email: EmailResponse) -> "SimpleEmailResponse":
        content: str | None = email.text_content
        if content is None or len(content) == 0:
            content = markdownify.markdownify(email.html_content)  # type: ignore[attr-defined]
        return SimpleEmailResponse(
            subject=email.subject,
            content=content or "no content",  # type: ignore[attr-defined]
            created_at=email.created_at,
            sender_email=email.sender_email or "unknown",
        )


class ListEmailResponse(BaseModel):
    emails: list[SimpleEmailResponse]


class SimpleSmsResponse(BaseModel):
    content: Annotated[str, Field(description="The body of the sms")]
    created_at: Annotated[dt.datetime, Field(description="The date and time the sms was sent")]
    sender_number: Annotated[str, Field(description="The phone number of the sender")]

    @staticmethod
    def from_sms(sms: SMSResponse) -> "SimpleSmsResponse":
        return SimpleSmsResponse(
            content=sms.body or "no content",
            created_at=sms.created_at,
            sender_number=sms.sender or "unknown",
        )


class ListSmsResponse(BaseModel):
    sms: list[SimpleSmsResponse]


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
    def read_emails(self, action: EmailReadAction) -> ExecutionResult:
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
            return ExecutionResult(
                action=action,
                success=True,
                message=f"No emails found in the inbox {time_str}",
                data=DataSpace.from_structured(ListEmailResponse(emails=[])),
            )
        emails: list[SimpleEmailResponse] = [SimpleEmailResponse.from_email(email) for email in raw_emails]
        return ExecutionResult(
            action=action,
            success=True,
            message=f"Successfully read {len(emails)} emails from the inbox {time_str}",
            data=DataSpace.from_structured(ListEmailResponse(emails=emails)),
        )

    @BaseTool.register(SmsReadAction)
    def read_sms(self, action: SmsReadAction) -> ExecutionResult:
        raw_sms: Sequence[SMSResponse] = []
        time_str = f"in the last {action.timedelta}" if action.timedelta is not None else ""
        for _ in range(self.nb_retries):
            raw_sms = self.persona.sms(
                only_unread=action.only_unread,
                timedelta=action.timedelta,
                limit=action.limit,
            )
            if len(raw_sms) > 0:
                break
            # if we have not found any emails, we wait for 5 seconds and retry
            logger.warning(
                f"No sms found in the inbox {time_str}, waiting for 5 seconds and retrying {self.nb_retries} times"
            )
            time.sleep(5)

        if len(raw_sms) == 0:
            return ExecutionResult(
                action=action,
                success=True,
                message=f"No emails found in the inbox {time_str}",
                data=DataSpace.from_structured(ListEmailResponse(emails=[])),
            )
        sms: list[SimpleSmsResponse] = [SimpleSmsResponse.from_sms(sms) for sms in raw_sms]
        return ExecutionResult(
            action=action,
            success=True,
            message=f"Successfully read {len(sms)} sms from the inbox {time_str}",
            data=DataSpace.from_structured(ListSmsResponse(sms=sms)),
        )
