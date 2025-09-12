from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Coroutine
from typing import Any, Callable, ClassVar, NotRequired, Unpack

from loguru import logger
from pydantic import BaseModel, Field, model_serializer
from pyotp.totp import TOTP
from typing_extensions import TypedDict, override

from notte_core.actions import (
    BaseAction,
    FallbackFillAction,
    FillAction,
    FormFillAction,
    MultiFactorFillAction,
    SelectDropdownOptionAction,
)
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.credentials.types import ValueWithPlaceholder, get_str_value
from notte_core.errors.actions import NoCredentialsFoundError
from notte_core.errors.processing import InvalidPlaceholderError
from notte_core.llms.types import TResponseFormat
from notte_core.profiling import profiler
from notte_core.utils.url import get_root_domain


class Credential(BaseModel):
    username: str | None
    email: str | None
    url: str


class Vault(BaseModel):
    name: str
    created_at: dt.datetime
    vault_id: str
    for_persona: bool = False


class LocatorAttributes(BaseModel):
    type: str | None
    autocomplete: str | None
    outerHTML: str | None


class CredentialField(BaseModel, ABC, frozen=True):  # pyright: ignore[reportUnsafeMultipleInheritance]
    value: str = Field(description="Stored value (sensitive)")
    alias: ClassVar[str] = Field(description="Keyword when setting value")
    exposed: ClassVar[bool] = Field(
        description="Whether to mention to the llm that the placeholder will be shown to it", default=False
    )
    placeholder_value: ClassVar[str] = Field(
        description="Value the llm has to set before being transcribed to actual value"
    )
    registry: ClassVar[dict[str, type[CredentialField]]] = {}
    placeholder_map: ClassVar[dict[str, type[CredentialField]]] = {}
    inverse_registry: ClassVar[dict[type[CredentialField], str]] = {}

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)  # pyright: ignore[reportArgumentType]

        if hasattr(cls, "alias") and isinstance(getattr(cls, "alias"), str):
            CredentialField.registry[cls.alias] = cls
            CredentialField.inverse_registry[cls] = cls.alias
            CredentialField.placeholder_map[cls.placeholder_value] = cls

    @abstractmethod
    def validate_element(self, attrs: LocatorAttributes) -> bool:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def default_instructions(placeholder: str) -> str:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, dic: dict[str, Any]):
        field_name = dic["field_name"]
        del dic["field_name"]
        return CredentialField.registry[field_name].model_validate(dic)

    @model_serializer
    def to_dict(self):
        dic = self.__dict__
        dic["field_name"] = self.alias
        return dic

    @staticmethod
    def all_placeholders() -> set[str]:
        placeholders: set[str] = set()
        for cred_type in CredentialField.registry.values():
            if hasattr(cred_type, "placeholder_value") and isinstance(getattr(cred_type, "placeholder_value"), str):
                placeholders.add(cred_type.placeholder_value)
        return placeholders

    def instructions(self) -> str:
        return self.default_instructions(self.placeholder_value)


class EmailField(CredentialField, frozen=True):
    alias: ClassVar[str] = "email"
    placeholder_value: ClassVar[str] = "user@example.org"
    field_autocomplete: ClassVar[str] = "username"

    @override
    def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in an email, use the value '{placeholder}'"


class UserNameField(CredentialField, frozen=True):
    alias: ClassVar[str] = "username"
    placeholder_value: ClassVar[str] = "cooljohnny1567"

    @override
    def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in a username , use the value '{placeholder}'"


class MFAField(CredentialField, frozen=True):
    alias: ClassVar[str] = "mfa_secret"
    placeholder_value: ClassVar[str] = "999779"

    @override
    def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in a 2FA code, use the value '{placeholder}'"


class PasswordField(CredentialField, frozen=True):
    alias: ClassVar[str] = "password"
    placeholder_value: ClassVar[str] = "mycoolpassword"
    field_autocomplete: ClassVar[str] = "current-password"

    @override
    def validate_element(self, attrs: LocatorAttributes) -> bool:
        return attrs.type == "password"

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in a password, use the value '{placeholder}'"


class RegexCredentialField(CredentialField, ABC, frozen=True):
    placeholder_value: ClassVar[str]
    field_autocomplete: ClassVar[str]
    field_regex: ClassVar[re.Pattern[str]]
    instruction_name: ClassVar[str]

    @override
    def validate_element(self, attrs: LocatorAttributes) -> bool:
        outerHTML = attrs.outerHTML or ""
        match = re.search(self.field_regex, outerHTML)
        return attrs.autocomplete == self.field_autocomplete or match is not None

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        try:
            return f"To fill in {placeholder}, use the value '{placeholder}'"
        except AttributeError:
            return ""


class CardHolderField(RegexCredentialField, frozen=True):
    alias: ClassVar[str] = "card_holder_name"
    placeholder_value: ClassVar[str] = "John Doe"
    field_autocomplete: ClassVar[str] = "cc-name"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(
        r'(cc|card).*-name|(cardholder)(?:name)?|autocomplete="name"', re.IGNORECASE
    )
    instruction_name: ClassVar[str] = "a payment form cardholder name"


class CardNumberField(RegexCredentialField, frozen=True):
    alias: ClassVar[str] = "card_number"
    placeholder_value: ClassVar[str] = "4242 4242 4242 4242"
    field_autocomplete: ClassVar[str] = "cc-number"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(r"(cc|card).*-?(num|number|no)|number|card-no", re.IGNORECASE)
    instruction_name: ClassVar[str] = "a payment form card number"


class CardCVVField(RegexCredentialField, frozen=True):
    exposed: ClassVar[bool] = True
    alias: ClassVar[str] = "card_cvv"
    placeholder_value: ClassVar[str] = "[CardCVVPlaceholder]"
    field_autocomplete: ClassVar[str] = "cc-csc"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(
        r"(cc|card|security|verification).*-(code|cvv|cvc|csc)|cvv|cvc|csc",
        re.IGNORECASE,
    )
    instruction_name: ClassVar[str] = "a payment form card CVV"


class CardFullExpirationField(RegexCredentialField, frozen=True):
    exposed: ClassVar[bool] = True
    alias: ClassVar[str] = "card_full_expiration"
    placeholder_value: ClassVar[str] = "[CardExpirationPlaceholder]"
    field_autocomplete: ClassVar[str] = "cc-exp"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(
        r"(cc|card).*-(exp|expiry|mm-yy|mm-yyyy)|expiration-date",
        re.IGNORECASE,
    )
    instruction_name: ClassVar[str] = "a payment form expiration date with month and year"


recursive_data = list["recursive_data"] | dict[str, "recursive_data"] | str | Any


class CredentialsDict(TypedDict, total=True):
    """Dictionary type for storing login credentials.

    At least one of email or username must be provided, but not both.
    Password is required. MFA secret is optional.

    Args:
        email: The email address used for login. Cannot be used with username.
        username: The username used for login. Cannot be used with email.
        password: The password for the account. Required.
        mfa_secret: Optional MFA/2FA secret key for generating one-time codes.
    """

    email: NotRequired[str]
    username: NotRequired[str]
    password: str
    mfa_secret: NotRequired[str]


def get_with_fallback(creds: CredentialsDict | CreditCardDict, key: str) -> str | None:
    correct = creds.get(key)

    if isinstance(correct, str):
        return correct

    retval = None
    fallback = None

    if key == EmailField.alias and isinstance(username := creds.get(UserNameField.alias), str):
        fallback = UserNameField.alias
        retval = username

    elif key == UserNameField.alias and isinstance(email := creds.get(EmailField.alias), str):
        fallback = EmailField.alias
        retval = email

    if retval is not None:
        logger.trace(f"Could not find creds for {key}, using {fallback} as fallback")

    return retval


class CreditCardDict(TypedDict, total=True):
    """Dictionary type for storing credit card information.

    Args:
        card_holder_name: The name of the credit card holder as it appears on the card
        card_number: The credit card number
        card_cvv: The 3 or 4 digit CVV security code on the back of the card
        card_full_expiration: The card's expiration date in MM/YY or MM/YYYY format
    """

    card_holder_name: str
    card_number: str
    card_cvv: str
    card_full_expiration: str


class BaseVault(ABC):
    """Base class for vault implementations that handle credential storage and retrieval."""

    def __init__(self):
        """Initialize the vault with an empty dictionary to track retrieved credentials."""
        self._retrieved_credentials: dict[str, CredentialsDict] = {}

    @staticmethod
    def credentials_dict_to_field(dic: CredentialsDict) -> list[CredentialField]:
        """Convert a credentials dictionary to a list of CredentialField objects.

        Args:
            dic: Dictionary containing credential key-value pairs

        Returns:
            List of CredentialField objects

        Raises:
            ValueError: If an invalid credential type is provided or if a value is not a string
        """
        creds: list[CredentialField] = []

        for key, value in dic.items():
            cred_class = CredentialField.registry.get(key)

            if cred_class is None:
                raise ValueError(f"Invalid credential type {key}. Valid types are: {CredentialField.registry.keys()}")

            if not isinstance(value, str):
                raise ValueError("Invalid credential type {type(value)}, should be str")

            creds.append(cred_class(value=value))
        return creds

    @staticmethod
    def credential_fields_to_dict(creds: list[CredentialField]) -> CredentialsDict:
        """Convert a list of CredentialField objects to a credentials dictionary.

        Args:
            creds: List of CredentialField objects

        Returns:
            Dictionary containing credential key-value pairs
        """
        dic: CredentialsDict = {}  # pyright: ignore[reportAssignmentType]

        for cred in creds:
            dic[CredentialField.inverse_registry[cred.__class__]] = cred.value

        return dic

    @abstractmethod
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        """Store credentials for a given URL.

        Args:
            url: The URL to store credentials for
            creds: Dictionary containing the credentials to store
        """
        pass

    def add_credentials(self, url: str, **kwargs: Unpack[CredentialsDict]) -> None:
        return asyncio.run(self.add_credentials_async(url, **kwargs))

    @profiler.profiled()
    async def add_credentials_async(self, url: str, **kwargs: Unpack[CredentialsDict]) -> None:
        """Store credentials for a given URL.

        Args:
            url: The URL to store credentials for
            **kwargs: Credential key-value pairs to store

        Raises:
            ValueError: If an invalid MFA secret code is provided
        """
        secret = kwargs.get("mfa_secret")
        if secret is not None:
            try:
                _ = TOTP(secret).now()
            except Exception as e:
                raise ValueError("Invalid MFA secret code: did you try to store an OTP instead of a secret?") from e

        return await self._add_credentials(url=url, creds=kwargs)

    def set_credit_card(self, **kwargs: Unpack[CreditCardDict]) -> None:
        return asyncio.run(self.set_credit_card_async(**kwargs))

    @profiler.profiled()
    @abstractmethod
    async def set_credit_card_async(self, **kwargs: Unpack[CreditCardDict]) -> None:
        """Store credit card information (one for the whole vault).

        Args:
            **kwargs: Credit card information to store
        """
        pass

    def get_credit_card(self) -> CreditCardDict:
        return asyncio.run(self.get_credit_card_async())

    @profiler.profiled()
    @abstractmethod
    async def get_credit_card_async(self) -> CreditCardDict:
        """Retrieve credit card information (one for the whole vault).

        Returns:
            Dictionary containing credit card information
        """
        pass

    def delete_credit_card(self) -> None:
        return asyncio.run(self.delete_credit_card_async())

    @profiler.profiled()
    @abstractmethod
    async def delete_credit_card_async(self) -> None:
        """Remove saved credit card information."""
        pass

    def delete_credentials(self, url: str) -> None:
        return asyncio.run(self.delete_credentials_async(url=url))

    @profiler.profiled()
    @abstractmethod
    async def delete_credentials_async(self, url: str) -> None:
        """Remove credentials for a given URL.

        Args:
            url: The URL to remove credentials for
        """
        pass

    def list_credentials(self) -> list[Credential]:
        return asyncio.run(self.list_credentials_async())

    @profiler.profiled()
    @abstractmethod
    async def list_credentials_async(self) -> list[Credential]:
        """List urls for which we hold credentials.

        Returns:
            List of Credential objects containing URL information
        """
        pass

    def has_credential(self, url: str) -> bool:
        return asyncio.run(self.has_credential_async(url=url))

    async def has_credential_async(self, url: str) -> bool:
        """Check whether we hold a credential for a given website.

        Args:
            url: The URL to check for credentials

        Returns:
            True if credentials exist for the URL, False otherwise
        """
        current_creds = await self.list_credentials_async()
        urls = {cred.url for cred in current_creds}
        return url in urls

    def add_credentials_from_env(self, url: str) -> None:
        return asyncio.run(self.add_credentials_from_env_async(url=url))

    async def add_credentials_from_env_async(self, url: str) -> None:
        """Add credentials from environment variables for a given URL.

        You should set the following environment variables for a given URL, i.e github.com:

        GITHUB_COM_EMAIL="user@example.org"
        GITHUB_COM_PASSWORD="mycoolpassword" # pragma: allowlist secret
        GITHUB_COM_USERNAME="cooljohnny1567"
        GITHUB_COM_MFA_SECRET="999779"

        Args:
            url: The URL to add credentials for

        Raises:
            ValueError: If no credentials are found in the environment variables
        """
        root_domain = get_root_domain(url)
        url_env = root_domain.replace(".", "_").upper()
        creds: CredentialsDict = {}  # pyright: ignore[reportAssignmentType]
        env_var_names: list[str] = []
        for key in CredentialField.registry.keys():
            env_var = f"{url_env}_{key.upper()}"
            env_var_names.append(env_var)
            env_var = os.getenv(env_var)
            if env_var is not None:
                creds[key] = env_var
        if len(creds) == 0:
            raise ValueError(
                f"No credentials found in the environment for {url}. Please set the following variables: {', '.join(env_var_names)}"
            )
        logger.trace(f"[Vault] add creds from env for {url_env}: {creds.keys()}")
        await self.add_credentials_async(url=url, **creds)

    def get_credentials(self, url: str) -> CredentialsDict | None:
        return asyncio.run(self.get_credentials_async(url=url))

    @profiler.profiled()  # noqa: F821
    async def get_credentials_async(self, url: str) -> CredentialsDict | None:
        """Get credentials for a given URL.

        Args:
            url: The URL to get credentials for

        Returns:
            Dictionary containing the credentials for the given URL, or None if no credentials exist
        """
        credentials = await self._get_credentials_impl(url)

        if credentials is None:
            return credentials

        # replace the one time passwords by their actual value
        updated_creds: CredentialsDict = {}  # pyright: ignore[reportAssignmentType]
        for key, cred in credentials.items():
            if CredentialField.registry.get(key) is MFAField:
                actual_val = TOTP(cred).now()  # pyright: ignore[reportArgumentType]
                updated_creds[key] = actual_val
            else:
                updated_creds[key] = cred

        # If credentials are found, track them
        self._retrieved_credentials[url] = updated_creds

        return updated_creds

    @abstractmethod
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        """Abstract method to be implemented by child classes for actual credential retrieval.

        Args:
            url: The URL to get credentials for

        Returns:
            Dictionary containing the credentials for the given URL, or None if no credentials exist
        """
        pass

    def past_credentials(self) -> dict[str, CredentialsDict]:
        """Get a copy of all previously retrieved credentials.

        Returns:
            Dictionary mapping URLs to their retrieved credentials
        """
        return self._retrieved_credentials.copy()

    @staticmethod
    def patch_structured_completion(
        arg_index: int,
        replacement_map_fn: Callable[..., dict[str, str]],
    ):
        def _patch_structured(
            func: Callable[..., Coroutine[Any, Any, TResponseFormat]],
        ) -> Callable[..., Coroutine[Any, Any, TResponseFormat]]:  # Return an async function
            async def patcher(
                *args: tuple[Any], **kwargs: dict[str, Any]
            ) -> TResponseFormat:  # Make this an async function
                arglist = list(args)
                replacement_map = replacement_map_fn()
                try:
                    original_string = json.dumps(arglist[arg_index], indent=2)
                except Exception as e:
                    raise ValueError(f"Invalid JSON object at index {arg_index}: {arglist[arg_index]}") from e
                og_dict = json.loads(original_string)

                arglist[arg_index] = BaseVault.recursive_replace_mapping(og_dict, replacement_map)  # type: ignore

                retval = await func(*arglist, **kwargs)

                return retval

            return patcher

        return _patch_structured

    @staticmethod
    def recursive_replace_mapping(data: recursive_data, replacement_map: dict[str, str]) -> recursive_data:
        """Recursively replace strings using a mapping dictionary.

        Args:
            data: The input data to process (dict, list, str, or any other type)
            replacement_map: A dictionary mapping strings to their replacements

        Returns:
            The modified data structure with replacements
        """
        if isinstance(data, dict):
            # don't replace in base64
            if "type" in data and data["type"] == "image_url":
                return data  # type: ignore

            # For dictionaries, replace strings in keys and values
            return {
                key: BaseVault.recursive_replace_mapping(value, replacement_map)  # type: ignore
                for key, value in data.items()  # type: ignore
            }
        elif isinstance(data, list):
            # For lists, recursively replace in each element
            return [BaseVault.recursive_replace_mapping(item, replacement_map) for item in data]  # type: ignore
        elif isinstance(data, str):
            # For strings, perform replacements using the mapping
            for old_string, new_string in replacement_map.items():
                data = data.replace(old_string, new_string)

            return data
        else:
            # For other types (int, float, etc.), return as-is
            return data

    def get_replacement_map(self) -> dict[str, str]:
        """Get the current map to replace text from previously used credentials back to their placeholder value.

        Returns:
            Dictionary mapping credential values to their placeholder values
        """
        return {  # pyright: ignore[reportReturnType]
            cred_value: CredentialField.registry[cred_key].placeholder_value
            for creds_dict in self.past_credentials().values()
            for cred_key, cred_value in creds_dict.items()
        }

    def contains_credentials(self, action: BaseAction) -> bool:
        """Check if the action contains credentials.

        Args:
            action: The action to check for credentials

        Returns:
            True if the action contains credential placeholders, False otherwise
        """
        json_action = action.model_dump_json()
        initial = False

        for placeholder_val in CredentialField.all_placeholders():
            initial |= placeholder_val in json_action

        return initial

    async def replace_credentials(
        self, action: BaseAction, attrs: LocatorAttributes, snapshot: BrowserSnapshot
    ) -> BaseAction:
        """Replace credentials in the action with actual values from the vault.

        Args:
            action: The action to replace credentials in
            attrs: Locator attributes for validation
            snapshot: Browser snapshot containing URL information

        Returns:
            Modified action with replaced credentials

        Raises:
            ValueError: If the action type is not supported or if no credentials are found
            InvalidPlaceholderError: If an invalid placeholder is used
        """
        # Get credentials for current domain

        if not isinstance(
            action, (MultiFactorFillAction, FillAction, FallbackFillAction, FormFillAction, SelectDropdownOptionAction)
        ):
            raise ValueError(f"Cant put credentials for action type {type(action)}")

        values_to_replace = action.value if isinstance(action, FormFillAction) else {"key": action.value}

        for action_key, original_action_value in values_to_replace.items():
            placeholder_value = get_str_value(original_action_value)
            cred_class = CredentialField.placeholder_map.get(placeholder_value)

            if cred_class is None:
                raise InvalidPlaceholderError(placeholder_value)

            cred_key = cred_class.alias

            if cred_class in (CardHolderField, CardNumberField, CardCVVField, CardFullExpirationField):
                creds_dict = await self.get_credit_card_async()
            else:
                try:
                    creds_dict = await self.get_credentials_async(snapshot.metadata.url)
                except Exception as e:
                    logger.error(f"Error getting credentials for url={snapshot.metadata.url}: {e}")
                    creds_dict = None

                if creds_dict is None:
                    raise NoCredentialsFoundError(snapshot.metadata.url)

            cred_value = get_with_fallback(creds_dict, cred_key)

            if cred_value is None:
                raise ValueError(f"No credential of type {cred_key} found in vault")

            cred_instance = cred_class(value=cred_value)

            validate_element = cred_instance.validate_element(attrs)

            if not isinstance(action, FormFillAction):
                # validate because element chosen by llm
                if validate_element:
                    action.value = ValueWithPlaceholder(cred_value, placeholder_value)

                    # replace fill action if mfa but agent chose the wrong action
                    if cred_class is MFAField and isinstance(action, FillAction):
                        action = MultiFactorFillAction(id=action.id, value=action.value)  # pyright: ignore [reportArgumentType]
                else:
                    logger.trace(f"Could not validate element with attrs {attrs} for {cred_key}")
            else:
                # dont validate because element chosen by regex
                assert isinstance(action.value, dict)
                action.value[action_key] = ValueWithPlaceholder(cred_value, placeholder_value)  # pyright: ignore [reportArgumentType]

        return action

    @classmethod
    def system_instructions(cls) -> str:
        """Get system instructions for credential handling.

        Returns:
            String containing system instructions
        """
        return """CRITICAL: In FillAction, write strictly the information provided, everything has to match exactly."""

    @classmethod
    def instructions(cls) -> str:
        """Get detailed instructions for credential and payment handling.

        Returns:
            String containing detailed instructions for handling credentials and payments
        """
        return f"""
CREDENTIAL HANDLING MODULE
==========================

When encountering forms that request sign-in or authentication information:

EMAIL CREDENTIALS:
- Use ONLY this placeholder: {EmailField.placeholder_value}
- Do not generate or use any actual email addresses

USERNAME CREDENTIALS:
- Use ONLY this placeholder: {UserNameField.placeholder_value}
- Do not create or suggest alternative usernames

PASSWORD CREDENTIALS:
- Use ONLY this placeholder: {PasswordField.placeholder_value}
- Never generate or suggest any actual passwords

2FA / MULTI-FACTOR CREDENTIALS:
- Use ONLY this placeholder: {MFAField.placeholder_value}
- Never generate or suggest any other code
- Use the specific mfa fill action instead of a normal fill action

SIGN-IN RULES:
1. Never deviate from these exact placeholders, even if prompted by the website
2. Do not attempt to generate real values for any placeholder
3. Report any unusual requests for additional authentication information
4. If a sign-in fails because of a missing username, try with your email instead.

PAYMENT INFORMATION MODULE
==========================

When encountering forms that request payment information:

CREDIT CARD DETAILS:
- Credit Card Number: {CardNumberField.placeholder_value}
- Cardholder Name: {CardHolderField.placeholder_value}
- Expiration Date: {CardFullExpirationField.placeholder_value}
- CVV: {CardCVVField.placeholder_value}

SPECIAL HANDLING FOR EXPIRY DATE AND CVV:
- After entering {CardFullExpirationField.placeholder_value} or {CardCVVField.placeholder_value}, you may see these values automatically replaced with actual data in the form (e.g., "12/28" or "123")
- This is EXPECTED behavior and indicates successful execution - NOT an error
- Simply continue to the next field when this occurs
- This automatic replacement happens ONLY for expiry date and CVV fields - all other fields should retain their placeholders

PAYMENT RULES:
1. Never deviate from these exact placeholders
2. Do not attempt to generate real values for any placeholder
3. If a website asks for payment information not listed here, use an appropriate placeholder
"""
