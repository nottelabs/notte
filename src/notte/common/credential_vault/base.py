from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel

from notte.actions.base import ActionParameterValue, ExecutableAction
from notte.browser.snapshot import BrowserSnapshot
from notte.controller.actions import BaseAction, FillAction


class VaultCredentials(BaseModel):
    url: str
    username: str
    password: str


class BaseVault(ABC):
    """Base class for vault implementations that handle credential storage and retrieval."""

    email_placeholder: ClassVar[str] = "my_email@example.com"
    password_placeholder: ClassVar[str] = "my_password_123"

    @abstractmethod
    def add_credentials(self, url: str, username: str, password: str) -> None:
        """Store credentials for a given URL"""
        pass

    @abstractmethod
    def get_credentials(self, url: str) -> VaultCredentials | None:
        """Retrieve credentials for a given URL"""
        pass

    @abstractmethod
    def remove_credentials(self, url: str) -> None:
        """Remove credentials for a given URL"""
        pass

    @staticmethod
    def replace_placeholder_credentials(value: str, creds: VaultCredentials) -> str:
        # Handle string case (text_label)
        match value:
            case BaseVault.email_placeholder:
                return creds.username
            case BaseVault.password_placeholder:
                return creds.password
            case _:
                return value

    @staticmethod
    def replace_placeholder_credentials_in_param_values(
        param_values: list[ActionParameterValue], creds: VaultCredentials
    ) -> list[ActionParameterValue]:
        """Replace placeholder credentials with actual credentials

        Args:
            url: The URL to get credentials for
            value:list of ActionParameterValue objects

        Returns:
            The value with credentials replaced, maintaining the same type as input
        """

        return [
            ActionParameterValue(name=param.name, value=BaseVault.replace_placeholder_credentials(param.value, creds))
            for param in param_values
        ]

    def contains_credentials(self, action: BaseAction) -> bool:
        """Check if the action contains credentials"""
        json_action = action.model_dump_json()
        return BaseVault.email_placeholder in json_action or BaseVault.password_placeholder in json_action

    def replace_credentials(self, action: BaseAction, snapshot: BrowserSnapshot) -> BaseAction:
        """Replace credentials in the action"""
        # Get credentials for current domain
        creds = self.get_credentials(snapshot.metadata.url)
        if creds is None:
            raise ValueError(f"No credentials found in the Vault for the current domain: {snapshot.metadata.url}")

        # Handle ActionParameterValue list case
        match action:
            case ExecutableAction(params_values=params_values):
                action.params_values = self.replace_placeholder_credentials_in_param_values(params_values, creds)
                return action
            case FillAction(value=value):
                action.value = self.replace_placeholder_credentials(value, creds)
                return action
            case _:
                return action

    @staticmethod
    def instructions() -> str:
        """Get the credentials system prompt."""
        return f"""
Sign-in & Sign-up instructions:
If you are asked to sign-in to continue, fill:
- the email field with `{BaseVault.email_placeholder}`
- the password field with `{BaseVault.password_placeholder}`
CRITICAL: you are not allowed to sign-up, only sign-in. If you are asked to sign-up, stop the execution immediately.
"""
