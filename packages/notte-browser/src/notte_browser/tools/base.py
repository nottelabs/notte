import datetime as dt
from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar, Literal, TypeVar, Unpack, final

from notte_core.actions import ActionParameter, DataAction
from notte_core.browser.observation import StepResult
from notte_core.data.space import DataSpace
from notte_sdk.endpoints.personas import Persona
from notte_sdk.types import EmailResponse, MessageReadRequest
from pydantic import BaseModel
from typing_extensions import override


class ToolAction(DataAction, ABC):
    pass


TToolAction = TypeVar("TToolAction", bound=ToolAction)

ToolInputs = tuple[TToolAction]
# ToolInputs = tuple[TToolAction, BrowserWindow, BrowserSnapshot]

ToolExecutionFunc = Callable[[Any, Unpack[ToolInputs[TToolAction]]], StepResult]
ToolExecutionFuncSelf = Callable[[Unpack[ToolInputs[TToolAction]]], StepResult]


class BaseTool(ABC):
    _tools: ClassVar[dict[type[ToolAction], ToolExecutionFunc[ToolAction]]] = {}  # pyright: ignore

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

    def get_action_registry(self) -> dict[str, type[ToolAction]]:
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


# #########################################################
# ################### PERSONA ACTIONS #####################
# #########################################################


class EmailReadAction(ToolAction, MessageReadRequest):
    type: Literal["email_read"] = "email_read"  # pyright: ignore [reportIncompatibleVariableOverride]
    description: str = "Read emails from the inbox."

    @override
    def execution_message(self) -> str:
        if self.timedelta is None:
            return "Successfully read emails from the inbox"
        else:
            return f"Successfully read emails from the inbox in the last {self.timedelta}"

    @override
    @staticmethod
    def example() -> "EmailReadAction":
        return EmailReadAction(
            timedelta=dt.timedelta(minutes=5),
            only_unread=True,
        )

    @property
    @override
    def param(self) -> ActionParameter | None:
        return ActionParameter(name="instructions", type="str")


class ListEmailResponse(BaseModel):
    emails: list[EmailResponse]


# #########################################################
# #################### PERSONA TOOLS ######################
# #########################################################


@final
class PersonaTool(BaseTool):
    def __init__(self, persona: Persona):
        super().__init__()
        self.persona = persona

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
        emails = self.persona.emails(
            only_unread=action.only_unread,
            timedelta=action.timedelta,
            limit=action.limit,
        )
        time_str = f"in the last {action.timedelta}" if action.timedelta is not None else ""
        if len(emails) == 0:
            return StepResult(
                success=True,
                message=f"No emails found in the inbox {time_str}",
                data=DataSpace.from_structured(ListEmailResponse(emails=[])),
            )
        return StepResult(
            success=True,
            message=f"Successfully read {len(emails)} emails from the inbox {time_str}",
            data=DataSpace.from_structured(ListEmailResponse(emails=[e for e in emails])),
        )
