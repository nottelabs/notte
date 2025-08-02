from notte_core.credentials.base import (
    BaseVault,
)
from typing_extensions import override

from notte_browser.playwright_async_api import Locator, Page
from notte_browser.window import ScreenshotMask


class VaultSecretsScreenshotMask(ScreenshotMask):
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
