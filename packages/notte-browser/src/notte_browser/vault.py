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
        if len(hidden_values) == 0:
            return []

        input_locator = page.locator("input")
        hidden_values_list = list(hidden_values)
        matching_indices: list[int] = await input_locator.evaluate_all(
            "(elements, hiddenValues) => elements.flatMap((el, i) => hiddenValues.includes(el.value) ? [i] : [])",
            hidden_values_list,
        )
        return [input_locator.nth(i) for i in matching_indices]
