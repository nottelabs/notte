import re

from notte_core.credentials.base import (
    BaseVault,
    CredentialField,
    PasswordField,
    RegexCredentialField,
    VaultCredentials,
)
from notte_core.credentials.types import ValueWithPlaceholder
from patchright.async_api import Locator, Page
from typing_extensions import override

from notte_browser.window import ScreenshotMask


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


class VaultScreetsScreenshotMask(ScreenshotMask):
    vault: BaseVault
    model_config = {"arbitrary_types_allowed": True}  # pyright: ignore[reportUnannotatedClassAttribute]

    @override
    async def mask(self, page: Page) -> list[Locator]:
        hidden_values = set(self.vault.get_replacement_map())
        hidden_locators: list[Locator] = []
        if len(hidden_values) > 0:
            # might be able to evaluate all locators, at once
            # fine for now
            for input_el in await page.locator("input").all():
                input_val = await input_el.evaluate("el => el.value")

                if input_val in hidden_values:
                    hidden_locators.append(input_el)
        return hidden_locators
