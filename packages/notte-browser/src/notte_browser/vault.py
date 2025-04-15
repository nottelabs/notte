import re

from notte_core.credentials.base import CredentialField, PasswordField, RegexCredentialField, VaultCredentials
from notte_core.credentials.types import ValueWithPlaceholder
from patchright.async_api import Locator


async def validate_element(locator: Locator, field: CredentialField) -> bool:
    match field:
        case PasswordField():
            attr_type = await locator.get_attribute("type")
            return attr_type == "password"
        case RegexCredentialField(field_regex=field_regex, field_autocomplete=field_autocomplete):
            autocomplete = await locator.get_attribute("autocomplete")
            outer_html = await locator.evaluate("el => el.outerHTML")
            match = re.search(field_regex, outer_html)
            return autocomplete == field_autocomplete or match is not None
        case _:
            return True


async def validate_replace_placeholder_credentials(
    value: str | ValueWithPlaceholder, locator: Locator, creds: VaultCredentials
) -> bool:
    for cred_value in creds.creds:
        if value == cred_value.placeholder_value:
            return await validate_element(locator, cred_value)
    return False
