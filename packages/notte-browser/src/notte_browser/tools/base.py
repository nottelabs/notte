import datetime as dt
import time
from abc import ABC, abstractmethod
from typing import Annotated, Any, Callable, ClassVar, TypeVar, Unpack, final

import markdownify  # type: ignore[import]
from loguru import logger
from notte_core.actions import DataAction, EmailReadAction
from notte_core.browser.observation import StepResult
from notte_core.data.space import DataSpace
from notte_sdk.endpoints.personas import Persona
from pydantic import BaseModel, Field
from typing_extensions import override

TDataAction = TypeVar("TDataAction", bound=DataAction)

ToolInputs = tuple[TDataAction]
# ToolInputs = tuple[TDataAction, BrowserWindow, BrowserSnapshot]

ToolExecutionFunc = Callable[[Any, Unpack[ToolInputs[TDataAction]]], StepResult]
ToolExecutionFuncSelf = Callable[[Unpack[ToolInputs[TDataAction]]], StepResult]


class BaseTool(ABC):
    _tools: ClassVar[dict[type[DataAction], ToolExecutionFunc[DataAction]]] = {}  # pyright: ignore

    @abstractmethod
    def instructions(self) -> str:
        pass

    @classmethod
    def register(
        cls, action: type[TDataAction]
    ) -> Callable[[ToolExecutionFunc[TDataAction]], ToolExecutionFunc[TDataAction]]:
        def decorator(func: ToolExecutionFunc[TDataAction]) -> ToolExecutionFunc[TDataAction]:
            cls._tools[action] = func  # type: ignore
            return func  # type: ignore

        return decorator  # type: ignore

    def tools(self) -> dict[type[DataAction], ToolExecutionFuncSelf[DataAction]]:
        return {
            action: self.get_tool(action)  # type: ignore
            for action in self._tools.keys()
        }

    def get_action_registry(self) -> dict[str, type[DataAction]]:
        return {action.name(): action for action in self._tools.keys()}

    def get_tool(self, action: type[TDataAction]) -> ToolExecutionFuncSelf[TDataAction] | None:
        func = self._tools.get(action)
        if func is None:
            return None

        def wrapper(*args: Unpack[ToolInputs[TDataAction]]) -> StepResult:
            return func(self, *args)

        return wrapper

    def execute(self, *inputs: Unpack[ToolInputs[TDataAction]]) -> StepResult:
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
        self.current_retries = nb_retries

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
        raw_emails = self.persona.emails(
            only_unread=action.only_unread,
            timedelta=action.timedelta,
            limit=action.limit,
        )
        time_str = f"in the last {action.timedelta}" if action.timedelta is not None else ""
        if len(raw_emails) == 0:
            logger.warning(
                f"No emails found in the inbox {time_str}, waiting for 5 seconds and retrying {self.current_retries} times"
            )
            if self.current_retries > 0:
                time.sleep(5)
                self.current_retries -= 1
                return self.read_emails(action)
        self.current_retries = self.nb_retries
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
