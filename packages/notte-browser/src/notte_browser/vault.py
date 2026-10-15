from collections.abc import Awaitable, Callable

from notte_core.actions import BaseAction, FormFillAction
from notte_core.browser.snapshot import BrowserSnapshot
from notte_core.credentials.base import (
    BaseVault,
    LocatorAttributes,
)
from notte_core.errors import VaultCredentialError
from typing_extensions import override

from notte_browser.playwright_async_api import Locator, Page
from notte_browser.window import ScreenshotMask


class VaultSecretsScreenshotMask(ScreenshotMask):
    def __init__(self, vault: BaseVault) -> None:
        self.vault: BaseVault = vault

    @override
    async def mask(self, page: Page) -> list[Locator]:
        hidden_values = set(self.vault.get_replacement_map())
        if len(hidden_values) == 0:
            return []

        input_locator = page.locator("input")
        hidden_values_list = list(hidden_values)
        matching_indices: list[int] = await input_locator.evaluate_all(
            "(elements, hiddenValues) => elements.flatMap((el, i) => hiddenValues.includes(el.value) ? [i] : [])",
            hidden_values_list,
        )
        return [input_locator.nth(i) for i in matching_indices]


async def resolve_vault_action(
    action: BaseAction,
    vault: BaseVault,
    snapshot: BrowserSnapshot,
    locate: Callable[[BaseAction], Awaitable[Locator | None]],
) -> BaseAction:
    """Substitute validated credentials, retaining locator metadata and masked values."""
    try:
        if isinstance(action, FormFillAction):
            attrs = LocatorAttributes(type=None, autocomplete=None, outerHTML=None)
            return await vault.replace_credentials(action, attrs, snapshot)

        locator = await locate(action)
        attrs = LocatorAttributes(type=None, autocomplete=None, outerHTML=None)
        if locator is not None:
            attrs = LocatorAttributes(
                type=await locator.get_attribute("type"),
                autocomplete=await locator.get_attribute("autocomplete"),
                outerHTML=await locator.evaluate("el => el.outerHTML"),
            )
        return await vault.replace_credentials(action, attrs, snapshot)
    except ValueError as e:
        # Credential field not found in vault (e.g., vault has email but action needs username).
        # Fail the action: executing it as is would type the raw placeholder into the page.
        raise VaultCredentialError(str(e)) from e
