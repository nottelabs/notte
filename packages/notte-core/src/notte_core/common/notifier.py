from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, final

from pydantic import BaseModel

if TYPE_CHECKING:
    from notte_sdk.types import AgentStatusResponse

typeAlias = type


class BaseNotifier(ABC, BaseModel):  # pyright: ignore [reportUnsafeMultipleInheritance]
    """Base class for notification implementations."""

    type: str

    @final
    class Config:
        arbitrary_types_allowed = True

    REGISTRY: ClassVar[dict[str, typeAlias["BaseNotifier"]]] = {}

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)  # pyright: ignore [reportArgumentType]

        if not inspect.isabstract(cls):
            name = cls.__name__
            if name in cls.REGISTRY:
                raise ValueError(f"Notifier {name} is duplicated")
            cls.REGISTRY[name] = cls

    @abstractmethod
    def send_message(self, text: str) -> None:
        """Send a message using the specific notification service."""
        pass

    def notify(self, task: str, result: AgentStatusResponse) -> None:
        """Send a notification about the task result.

        Args:
            task: The task description
            result: The agent's response to be sent
        """
        message = f"""
Notte Agent Report 🌙

Task Details:
-------------
Task: {task}
Status: {"✅ Success" if result.success else "❌ Failed"}


Agent Response:
--------------
{result.answer}

Powered by Notte 🌒"""
        self.send_message(text=message)
