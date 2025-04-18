from __future__ import annotations

import json
import logging
import re
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar, Unpack

from pydantic import BaseModel, Field, field_validator, model_serializer
from pyotp.totp import TOTP
from typing_extensions import TypedDict, override

from notte_core.actions.base import ActionParameterValue, ExecutableAction
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.controller.actions import BaseAction, FillAction
from notte_core.credentials.types import ValueWithPlaceholder
from notte_core.llms.engine import TResponseFormat


class LocatorAttributes(BaseModel):
    type: str | None
    autocomplete: str | None
    outerHTML: str | None


class CredentialField(BaseModel, ABC, frozen=True):  # type: ignore[reportUnsafeMultipleInheritance]
    value: str
    alias: ClassVar[str]
    singleton: ClassVar[bool] = False
    placeholder_value: ClassVar[str]
    registry: ClassVar[dict[str, type[CredentialField]]] = {}
    inverse_registry: ClassVar[dict[type[CredentialField], str]] = {}

    def __init_subclass__(cls, **kwargs: dict[Any, Any]):
        super().__init_subclass__(**kwargs)  # type: ignore

        if hasattr(cls, "alias"):
            CredentialField.registry[cls.alias] = cls
            CredentialField.inverse_registry[cls] = cls.alias

    @abstractmethod
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
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
            if hasattr(cred_type, "placeholder_value"):
                placeholders.add(cred_type.placeholder_value)
        return placeholders

    def instructions(self) -> str:
        if self.singleton:
            return self.default_instructions(self.value)
        return self.default_instructions(self.placeholder_value)


class EmailField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = False
    alias: ClassVar[str] = "email"
    placeholder_value: ClassVar[str] = "user@example.org"
    field_autocomplete: ClassVar[str] = "username"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in an email, use the value '{placeholder}'"


class PhoneNumberField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = False
    alias: ClassVar[str] = "phone_number"
    placeholder_value: ClassVar[str] = "8005550175"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return (
            f"To fill in a phone number, use the value '{placeholder}'. "
            + "Your country code is +1 (from the United States)."
        )


class FirstNameField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = False
    alias: ClassVar[str] = "first_name"
    placeholder_value: ClassVar[str] = "Johnny"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in your first name, use the value '{placeholder}'"


class LastNameField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = False
    alias: ClassVar[str] = "last_name"
    placeholder_value: ClassVar[str] = "Dough"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in your last name, use the value '{placeholder}'"


class UserNameField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = False
    alias: ClassVar[str] = "username"
    placeholder_value: ClassVar[str] = "cooljohnny1567"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in a username , use the value '{placeholder}'"


class MFAField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = False
    alias: ClassVar[str] = "mfa_secret"
    placeholder_value: ClassVar[str] = "999779"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in a 2FA code, use the value '{placeholder}'"


class DoBDayField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = True
    alias: ClassVar[str] = "day_of_birth"
    placeholder_value: ClassVar[str] = "01"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill the day from your date of birth, use the value '{placeholder}'."


class DoBMonthField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = True
    alias: ClassVar[str] = "month_of_birth"
    placeholder_value: ClassVar[str] = "01"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill the month from your date of birth, use the value '{placeholder}'."


class DoBYearField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = True
    alias: ClassVar[str] = "year_of_birth"
    placeholder_value: ClassVar[str] = "1990"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return True

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill the year from your date of birth, use the value '{placeholder}'."


class PasswordField(CredentialField, frozen=True):
    singleton: ClassVar[bool] = False
    alias: ClassVar[str] = "password"
    placeholder_value: ClassVar[str] = "mycoolpassword"
    field_autocomplete: ClassVar[str] = "current-password"

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
        return attrs.type == "password"

    @override
    @staticmethod
    def default_instructions(placeholder: str) -> str:
        return f"To fill in a password, use the value '{placeholder}'"


class RegexCredentialField(CredentialField, ABC, frozen=True):
    singleton: ClassVar[bool] = False
    placeholder_value: ClassVar[str]
    field_autocomplete: ClassVar[str]
    field_regex: ClassVar[re.Pattern[str]]
    instruction_name: ClassVar[str]

    @override
    async def validate_element(self, attrs: LocatorAttributes) -> bool:
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
    singleton: ClassVar[bool] = True
    alias: ClassVar[str] = "card_holder_name"
    placeholder_value: ClassVar[str] = "John Doe"
    field_autocomplete: ClassVar[str] = "cc-name"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(
        r'(cc|card).*-name|(cardholder)(?:name)?|autocomplete="name"', re.IGNORECASE
    )
    instruction_name: ClassVar[str] = "a payment form cardholder name"


class CardNumberField(RegexCredentialField, frozen=True):
    singleton: ClassVar[bool] = False
    alias: ClassVar[str] = "card_number"
    placeholder_value: ClassVar[str] = "4242 4242 4242 4242"
    field_autocomplete: ClassVar[str] = "cc-number"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(r"(cc|card).*-?(num|number|no)|number|card-no", re.IGNORECASE)
    instruction_name: ClassVar[str] = "a payment form card number"


class CardCVVField(RegexCredentialField, frozen=True):
    singleton: ClassVar[bool] = True
    alias: ClassVar[str] = "card_cvv"
    placeholder_value: ClassVar[str] = "444"
    field_autocomplete: ClassVar[str] = "cc-csc"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(
        r"(cc|card|security|verification).*-(code|cvv|cvc|csc)|cvv|cvc|csc",
        re.IGNORECASE,
    )
    instruction_name: ClassVar[str] = "a payment form card CVV"


class CardFullExpirationField(RegexCredentialField, frozen=True):
    singleton: ClassVar[bool] = True
    alias: ClassVar[str] = "card_full_expiration"
    placeholder_value: ClassVar[str] = "04/25"
    field_autocomplete: ClassVar[str] = "cc-exp"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(
        r"(cc|card).*-(exp|expiry|mm-yy|mm-yyyy)|expiration-date",
        re.IGNORECASE,
    )
    instruction_name: ClassVar[str] = "a payment form expiration date with month and year"


class CardMonthExpirationField(RegexCredentialField, frozen=True):
    singleton: ClassVar[bool] = True
    alias: ClassVar[str] = "card_month_expiration"
    placeholder_value: ClassVar[str] = "05"
    field_autocomplete: ClassVar[str] = "cc-exp-month"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(
        r'(cc-exp|card-exp|card-expiration|card-expire|expire|expiry).*-(month|mm|mo)|label="mm"',
        re.IGNORECASE,
    )
    instruction_name: ClassVar[str] = "a payment form expiration month (no year)"


class CardYearExpirationField(RegexCredentialField, frozen=True):
    singleton: ClassVar[bool] = True
    alias: ClassVar[str] = "card_year_expiration"
    placeholder_value: ClassVar[str] = "25"
    field_autocomplete: ClassVar[str] = "cc-exp-year"
    field_regex: ClassVar[re.Pattern[str]] = re.compile(
        r'(cc-exp|card-exp|card-expiration|card-expire|expire|expiry).*-(year|yr|yy|yyyy)|label="yy"',
        re.IGNORECASE,
    )
    instruction_name: ClassVar[str] = "a payment form expiration year (no month)"


class VaultCredentials(BaseModel):
    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    url: str
    creds: list[CredentialField]
    id: str = Field(default_factory=generate_id)

    @field_validator("creds", mode="after")
    @classmethod
    def ensure_one_per_type(cls, value: list[CredentialField]) -> list[CredentialField]:
        creds: set[str] = set()
        for cred in value:
            name = cred.__class__.__name__
            if name in creds:
                raise ValueError(f"Can't have two {name} fields for a single domain")
            creds.add(name)

        return value


recursive_data = list["recursive_data"] | dict[str, "recursive_data"] | str | Any


class CredentialsDict(TypedDict, total=False):
    email: str
    phone_number: str
    first_name: str
    last_name: str
    username: str
    mfa_secret: str
    day_of_birth: str
    month_of_birth: str
    year_of_birth: str
    password: str
    card_holder_name: str
    card_number: str
    card_cvv: str
    card_full_expiration: str
    card_month_expiration: str
    card_year_expiration: str


class BaseVault(ABC):
    """Base class for vault implementations that handle credential storage and retrieval."""

    _retrieved_credentials: dict[str, VaultCredentials] = {}

    @abstractmethod
    async def _add_credentials(self, creds: VaultCredentials) -> None:
        """Store credentials for a given URL"""
        pass

    @staticmethod
    def credentials_dict_to_field(dic: CredentialsDict) -> list[CredentialField]:
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
        dic: CredentialsDict = {}

        for cred in creds:
            dic[CredentialField.inverse_registry[cred.__class__]] = cred.value

        return dic

    async def add_credentials(self, url: str | None, **kwargs: Unpack[CredentialsDict]) -> None:
        """Store credentials for a given URL"""
        creds = BaseVault.credentials_dict_to_field(kwargs)

        if url is None:
            return await self._set_singleton_credentials(creds=creds)
        return await self._add_credentials(VaultCredentials(url=url, creds=creds))

    async def set_singleton_credentials(self, **kwargs: Unpack[CredentialsDict]) -> None:
        return await self.add_credentials(url=None, **kwargs)

    @abstractmethod
    async def _set_singleton_credentials(self, creds: list[CredentialField]) -> None:
        """Set credentials which are shared across all urls, not hidden"""
        pass

    @abstractmethod
    async def remove_credentials(self, url: str) -> None:
        """Remove credentials for a given URL"""
        pass

    @abstractmethod
    async def get_singleton_credentials(self) -> list[CredentialField]:
        """Credentials which are shared across all urls, and aren't hidden"""
        pass

    async def get_credentials(self, url: str) -> VaultCredentials | None:
        credentials = await self._get_credentials_impl(url)

        if credentials is None:
            return credentials

        # replace the one time passwords by their actual value
        updated_creds: list[CredentialField] = []
        for cred in credentials.creds:
            if not isinstance(cred, MFAField):
                updated_creds.append(cred)
            else:
                actual_val = TOTP(cred.value).now()
                updated_creds.append(MFAField(value=actual_val))
        vault_creds = VaultCredentials(url=credentials.url, creds=updated_creds)

        # If credentials are found, track them
        self._retrieved_credentials[url] = vault_creds

        return vault_creds

    @abstractmethod
    async def _get_credentials_impl(self, url: str) -> VaultCredentials | None:
        """
        Abstract method to be implemented by child classes for actual credential retrieval.

        Child classes must implement the actual credential retrieval logic here.
        The base class's get_credentials method will handle tracking.
        """
        pass

    def past_credentials(self) -> dict[str, VaultCredentials]:
        return self._retrieved_credentials.copy()

    @staticmethod
    def patch_structured_completion(arg_index: int, replacement_map_fn: Callable[..., dict[str, str]]):
        def _patch_structured(
            func: Callable[..., TResponseFormat],
        ) -> Callable[..., TResponseFormat]:
            def patcher(*args: tuple[Any], **kwargs: dict[str, Any]):
                arglist = list(args)
                replacement_map = replacement_map_fn()

                original_string = json.dumps(arglist[arg_index], indent=2)
                og_dict = json.loads(original_string)

                arglist[arg_index] = BaseVault.recursive_replace_mapping(og_dict, replacement_map)  # type: ignore

                retval = func(*arglist, **kwargs)

                return retval

            return patcher

        return _patch_structured

    @staticmethod
    def recursive_replace_mapping(data: recursive_data, replacement_map: dict[str, str]) -> recursive_data:
        """
        Recursively replace strings using a mapping dictionary.

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

    @staticmethod
    async def replace_placeholder_credentials(
        value: str | ValueWithPlaceholder, attrs: LocatorAttributes, creds: VaultCredentials
    ) -> ValueWithPlaceholder | str:
        # Handle string case (text_label)
        val: str | ValueWithPlaceholder | None = None
        for cred_value in creds.creds:
            if value == cred_value.placeholder_value:
                validate_element = await cred_value.validate_element(attrs)
                if not validate_element:
                    logging.warning(f"Could not validate element with attrs {attrs} for {cred_value.__class__}")

                else:
                    if not cred_value.singleton:
                        val = ValueWithPlaceholder(cred_value.value, cred_value.placeholder_value)
                    else:
                        val = cred_value.value

        if val is None:
            logging.warning(f"Could not find any credential that matches with {value}")
            return value

        return val

    @staticmethod
    async def replace_placeholder_credentials_in_param_values(
        param_values: list[ActionParameterValue],
        attrs: LocatorAttributes,
        creds: VaultCredentials,
    ) -> list[ActionParameterValue]:
        """Replace placeholder credentials with actual credentials

        Args:
            url: The URL to get credentials for
            value:list of ActionParameterValue objects

        Returns:
            The value with credentials replaced, maintaining the same type as input
        """

        return [
            ActionParameterValue(
                name=param.name,
                value=await BaseVault.replace_placeholder_credentials(param.value, attrs, creds),
            )
            for param in param_values
        ]

    def get_replacement_map(self) -> dict[str, str]:
        """Gets the current map to replace text from previously used credentials
        back to their placeholder value.
        """
        return {
            value.value: value.placeholder_value
            for creds in self.past_credentials().values()
            for value in creds.creds
            if not value.singleton
        }

    def contains_credentials(self, action: BaseAction) -> bool:
        """Check if the action contains credentials"""
        json_action = action.model_dump_json()
        initial = False

        for placeholder_val in CredentialField.all_placeholders():
            initial |= placeholder_val in json_action

        return initial

    async def replace_credentials(
        self, action: BaseAction, attrs: LocatorAttributes, snapshot: BrowserSnapshot
    ) -> BaseAction:
        """Replace credentials in the action"""
        # Get credentials for current domain
        creds = await self.get_credentials(snapshot.metadata.url)
        if creds is None:
            raise ValueError(f"No credentials found in the Vault for the current domain: {snapshot.metadata.url}")

        # Handle ActionParameterValue list case
        match action:
            case ExecutableAction(params_values=params_values):
                action.params_values = await self.replace_placeholder_credentials_in_param_values(
                    params_values, attrs, creds
                )
                return action
            case FillAction(value=value):
                action.value = await self.replace_placeholder_credentials(value, attrs, creds)
                return action
            case _:
                return action

    def system_instructions(self) -> str:
        return """CRITICAL: In FillAction, write strictly the information provided, everything has to match exactly."""

    async def instructions(self) -> str:
        """Get the credentials system prompt."""
        website_instructs = """Sign-in & Sign-up instructions:
If you are asked for credentials for signing in or up:"""

        for cred in await self.get_singleton_credentials():
            website_instructs += cred.instructions()
            website_instructs += "\n"

        for cred_type in CredentialField.registry.values():
            if not cred_type.singleton and hasattr(cred_type, "placeholder_value"):
                website_instructs += cred_type.default_instructions(cred_type.placeholder_value)
                website_instructs += "\n"

        return website_instructs
